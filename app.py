from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import configparser
import re
from pathlib import Path
import PyPDF2
import logging
from urllib.parse import unquote

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFSearcher:
    def __init__(self, config_file='config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        # Remover comillas del directorio si las tiene
        raw_directory = self.config.get('PATHS', 'search_directory', fallback='./pdfs')
        self.search_directory = raw_directory.strip('"').strip("'")
        self.case_sensitive = self.config.getboolean('SEARCH', 'case_sensitive', fallback=False)
        self.search_subdirectories = self.config.getboolean('SEARCH', 'search_subdirectories', fallback=True)
        self.max_results = self.config.getint('SEARCH', 'max_results', fallback=100)
        
    def extract_text_from_pdf(self, pdf_path):
        """Extrae texto de un archivo PDF"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                # Limitar a las primeras 5 páginas para mejorar rendimiento
                max_pages = min(len(pdf_reader.pages), 5)
                for i in range(max_pages):
                    page_text = pdf_reader.pages[i].extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                return text.lower() if not self.case_sensitive else text
        except Exception as e:
            logger.error(f"Error leyendo PDF {pdf_path}: {str(e)}")
            return ""
    
    def search_in_filename(self, filename, search_terms):
        """Busca términos en el nombre del archivo"""
        filename_search = filename.lower() if not self.case_sensitive else filename
        matches = []
        
        for term_type, term_value in search_terms.items():
            if term_value:
                term_search = term_value.lower() if not self.case_sensitive else term_value
                if term_search in filename_search:
                    matches.append(term_type)
                    
        return matches
    
    def search_in_content(self, content, search_terms):
        """Busca términos en el contenido del PDF"""
        matches = []
        
        for term_type, term_value in search_terms.items():
            if term_value:
                # Preparar término de búsqueda
                term_search = term_value.lower() if not self.case_sensitive else term_value
                
                # Múltiples patrones de búsqueda para mayor flexibilidad
                patterns = [
                    term_search,  # Búsqueda exacta
                    re.escape(term_search),  # Búsqueda con caracteres especiales escapados
                    term_search.replace('-', r'[-\s]?'),  # Permitir guiones o espacios
                    term_search.replace('/', r'[/\s]?'),  # Permitir barras o espacios
                    term_search.replace(' ', r'\s+'),  # Múltiples espacios
                ]
                
                found = False
                for pattern in patterns:
                    try:
                        if re.search(pattern, content, re.IGNORECASE if not self.case_sensitive else 0):
                            matches.append(term_type)
                            found = True
                            break
                    except re.error:
                        continue
                        
        return matches
    
    def search_pdfs(self, expediente="", sello="", caratula="", match_all=False):
        """
        Busca PDFs que coincidan con los criterios especificados
        
        Args:
            expediente: Número de expediente a buscar
            sello: Número de sello a buscar
            caratula: Carátula a buscar
            match_all: Si True, debe coincidir con todos los términos; si False, con al menos uno
        """
        search_terms = {
            'expediente': expediente.strip(),
            'sello': sello.strip(),
            'caratula': caratula.strip()
        }
        
        # Filtrar términos vacíos
        search_terms = {k: v for k, v in search_terms.items() if v}
        
        if not search_terms:
            return []
        
        results = []
        search_path = Path(self.search_directory)
        
        if not search_path.exists():
            logger.error(f"Directorio de búsqueda no existe: {self.search_directory}")
            raise FileNotFoundError(f"Directorio de búsqueda no encontrado: {self.search_directory}")
        
        # Buscar archivos PDF
        if self.search_subdirectories:
            pdf_files = list(search_path.rglob("*.pdf"))
        else:
            pdf_files = list(search_path.glob("*.pdf"))
        
        logger.info(f"Buscando en {len(pdf_files)} archivos PDF...")
        
        for i, pdf_file in enumerate(pdf_files):
            if len(results) >= self.max_results:
                logger.warning(f"Se alcanzó el límite de {self.max_results} resultados")
                break
                
            try:
                filename = pdf_file.name
                relative_path = str(pdf_file.relative_to(search_path))
                
                # Buscar en nombre de archivo
                filename_matches = self.search_in_filename(filename, search_terms)
                
                # Buscar en contenido solo si no se encontró en el nombre del archivo
                # o si se requiere coincidencia con todos los términos
                content_matches = []
                if not filename_matches or match_all:
                    content = self.extract_text_from_pdf(pdf_file)
                    content_matches = self.search_in_content(content, search_terms)
                
                # Combinar coincidencias
                all_matches = list(set(filename_matches + content_matches))
                
                # Verificar si cumple con los criterios de búsqueda
                should_include = False
                if match_all:
                    # Todos los términos deben estar presentes
                    required_matches = set(search_terms.keys())
                    found_matches = set(all_matches)
                    should_include = required_matches.issubset(found_matches)
                else:
                    # Al menos un término debe estar presente
                    should_include = len(all_matches) > 0
                
                if should_include:
                    result = {
                        'filename': filename,
                        'path': str(pdf_file),
                        'relative_path': relative_path,
                        'matches': all_matches,
                        'match_details': {
                            'filename_matches': filename_matches,
                            'content_matches': content_matches
                        },
                        'size': pdf_file.stat().st_size,
                        'modified': pdf_file.stat().st_mtime,
                        'relevance_score': len(all_matches)
                    }
                    
                    results.append(result)
                    
                # Log de progreso cada 10 archivos
                if (i + 1) % 10 == 0:
                    logger.info(f"Procesados {i + 1}/{len(pdf_files)} archivos...")
                    
            except Exception as e:
                logger.error(f"Error procesando {pdf_file}: {str(e)}")
                continue
        
        # Ordenar por relevancia (más coincidencias primero) y luego por fecha de modificación
        results.sort(key=lambda x: (x['relevance_score'], x['modified']), reverse=True)
        
        logger.info(f"Búsqueda completada. {len(results)} resultados encontrados.")
        return results

# Instanciar el buscador
searcher = PDFSearcher()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    
    expediente = data.get('expediente', '')
    sello = data.get('sello', '')
    caratula = data.get('caratula', '')
    match_all = data.get('match_all', False)  # Parámetro opcional
    
    try:
        results = searcher.search_pdfs(expediente, sello, caratula, match_all)
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'search_params': {
                'expediente': expediente,
                'sello': sello,
                'caratula': caratula,
                'match_all': match_all
            }
        })
    
    except Exception as e:
        logger.error(f"Error en búsqueda: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/download')
def download():
    """Endpoint para descargar/abrir archivos PDF"""
    file_path = request.args.get('file')
    
    if not file_path:
        abort(400, description="Parámetro 'file' requerido")
    
    # Decodificar la ruta del archivo
    file_path = unquote(file_path)
    
    # Verificar que el archivo existe y está dentro del directorio permitido
    full_path = Path(file_path)
    search_path = Path(searcher.search_directory).resolve()
    
    try:
        # Verificar que la ruta está dentro del directorio de búsqueda (seguridad)
        full_path.resolve().relative_to(search_path)
    except ValueError:
        abort(403, description="Acceso denegado")
    
    if not full_path.exists():
        abort(404, description="Archivo no encontrado")
    
    if not full_path.suffix.lower() == '.pdf':
        abort(400, description="Solo se permiten archivos PDF")
    
    try:
        return send_file(
            full_path,
            as_attachment=False,  # Abrir en el navegador en lugar de descargar
            download_name=full_path.name,
            mimetype='application/pdf'
        )
    except Exception as e:
        logger.error(f"Error enviando archivo {full_path}: {str(e)}")
        abort(500, description="Error interno del servidor")

@app.route('/static/images/<filename>')
def serve_image(filename):
    """Endpoint para servir imágenes estáticas"""
    try:
        images_dir = os.path.join(app.static_folder, 'images')
        return send_file(os.path.join(images_dir, filename))
    except Exception as e:
        logger.error(f"Error sirviendo imagen {filename}: {str(e)}")
        abort(404)

@app.route('/config')
def get_config():
    return jsonify({
        'search_directory': searcher.search_directory,
        'case_sensitive': searcher.case_sensitive,
        'search_subdirectories': searcher.search_subdirectories,
        'max_results': searcher.max_results
    })

@app.route('/health')
def health_check():
    """Endpoint de verificación de estado"""
    return jsonify({
        'status': 'healthy',
        'search_directory_exists': Path(searcher.search_directory).exists(),
        'version': '1.0.0'
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Recurso no encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == '__main__':
    # Configuración del servidor desde config.ini
    debug = searcher.config.getboolean('SERVER', 'debug', fallback=True)
    host = searcher.config.get('SERVER', 'host', fallback='0.0.0.0')
    port = searcher.config.getint('SERVER', 'port', fallback=5000)
    
    # Verificar que el directorio de búsqueda existe
    search_dir = Path(searcher.search_directory)
    if not search_dir.exists():
        logger.warning(f"El directorio de búsqueda no existe: {searcher.search_directory}")
        logger.info(f"Creando directorio: {searcher.search_directory}")
        search_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Iniciando servidor en http://{host}:{port}")
    logger.info(f"Directorio de búsqueda: {searcher.search_directory}")
    
    app.run(debug=debug, host=host, port=port)