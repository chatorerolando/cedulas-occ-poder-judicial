class PDFSearchApp {
    constructor() {
        this.initializeElements();
        this.bindEvents();
        this.loadConfig();
    }

    initializeElements() {
        // Formulario y campos
        this.searchForm = document.getElementById('searchForm');
        this.expedienteInput = document.getElementById('expediente');
        this.selloInput = document.getElementById('sello');
        this.caratulaInput = document.getElementById('caratula');
        this.searchBtn = document.getElementById('searchBtn');
        this.clearBtn = document.getElementById('clearBtn');

        // Elementos de resultados
        this.resultsSection = document.getElementById('resultsSection');
        this.resultsContainer = document.getElementById('resultsContainer');
        this.resultsCount = document.getElementById('resultsCount');

        // Elementos de estado
        this.loading = document.getElementById('loading');
        this.errorMessage = document.getElementById('errorMessage');
        this.errorText = document.getElementById('errorText');
        this.searchDirectory = document.getElementById('searchDirectory');
    }

    bindEvents() {
        this.searchForm.addEventListener('submit', (e) => this.handleSearch(e));
        this.clearBtn.addEventListener('click', () => this.clearForm());
        
        // Búsqueda en tiempo real (opcional)
        const inputs = [this.expedienteInput, this.selloInput, this.caratulaInput];
        inputs.forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.handleSearch(e);
                }
            });
        });
    }

    async loadConfig() {
        try {
            const response = await fetch('/config');
            const config = await response.json();
            this.searchDirectory.textContent = config.search_directory;
        } catch (error) {
            console.error('Error cargando configuración:', error);
            this.searchDirectory.textContent = 'Error al cargar configuración';
        }
    }

    async handleSearch(e) {
        e.preventDefault();
        
        const searchData = {
            expediente: this.expedienteInput.value.trim(),
            sello: this.selloInput.value.trim(),
            caratula: this.caratulaInput.value.trim()
        };

        // Validar que al menos un campo tenga contenido
        if (!searchData.expediente && !searchData.sello && !searchData.caratula) {
            this.showError('Por favor, ingrese al menos un criterio de búsqueda.');
            return;
        }

        this.showLoading();
        this.hideError();
        this.hideResults();

        try {
            const response = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(searchData)
            });

            const result = await response.json();

            if (result.success) {
                this.displayResults(result.results, result.total);
            } else {
                this.showError(result.error || 'Error en la búsqueda');
            }
        } catch (error) {
            console.error('Error en la búsqueda:', error);
            this.showError('Error de conexión. Por favor, intente nuevamente.');
        } finally {
            this.hideLoading();
        }
    }

    displayResults(results, total) {
        this.resultsCount.textContent = `${total} documento${total !== 1 ? 's' : ''} encontrado${total !== 1 ? 's' : ''}`;
        
        if (total === 0) {
            this.resultsContainer.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-search" style="font-size: 3rem; color: #ccc; margin-bottom: 20px;"></i>
                    <h3>No se encontraron documentos</h3>
                    <p>Intente con otros criterios de búsqueda.</p>
                </div>
            `;
        } else {
            this.resultsContainer.innerHTML = results.map(result => this.createResultItem(result)).join('');
            
            // Agregar eventos de click para abrir archivos
            this.addResultClickEvents();
        }
        
        this.showResults();
    }

    createResultItem(result) {
        const matches = result.matches.map(match => 
            `<span class="match-tag">${this.getMatchDisplayName(match)}</span>`
        ).join('');

        const fileSize = this.formatFileSize(result.size);
        const modifiedDate = new Date(result.modified * 1000).toLocaleString('es-ES');

        return `
            <div class="result-item" data-path="${result.path}">
                <div class="result-header">
                    <div class="result-title">
                        <i class="fas fa-file-pdf"></i>
                        ${result.filename}
                    </div>
                </div>
                
                <div class="result-path">
                    <i class="fas fa-folder"></i> ${result.relative_path}
                </div>
                
                <div class="result-matches">
                    ${matches}
                </div>
                
                <div class="result-meta">
                    <span><i class="fas fa-weight-hanging"></i> ${fileSize}</span>
                    <span><i class="fas fa-calendar"></i> Modificado: ${modifiedDate}</span>
                </div>
            </div>
        `;
    }

    addResultClickEvents() {
        const resultItems = document.querySelectorAll('.result-item');
        resultItems.forEach(item => {
            item.addEventListener('click', () => {
                const filePath = item.dataset.path;
                this.openFile(filePath);
            });
        });
    }

    openFile(filePath) {
        // Crear un enlace temporal para descargar/abrir el archivo
        // Nota: Esto requerirá implementar un endpoint adicional en Flask
        const link = document.createElement('a');
        link.href = `/download?file=${encodeURIComponent(filePath)}`;
        link.target = '_blank';
        link.click();
    }

    getMatchDisplayName(match) {
        const displayNames = {
            'expediente': 'Expediente',
            'sello': 'Sello',
            'caratula': 'Carátula'
        };
        return displayNames[match] || match;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    clearForm() {
        this.expedienteInput.value = '';
        this.selloInput.value = '';
        this.caratulaInput.value = '';
        this.hideResults();
        this.hideError();
        this.expedienteInput.focus();
    }

    showLoading() {
        this.loading.style.display = 'block';
        this.searchBtn.disabled = true;
        this.searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
    }

    hideLoading() {
        this.loading.style.display = 'none';
        this.searchBtn.disabled = false;
        this.searchBtn.innerHTML = '<i class="fas fa-search"></i> Buscar';
    }

    showResults() {
        this.resultsSection.style.display = 'block';
        this.resultsSection.classList.add('fade-in');
        
        // Scroll suave a los resultados
        this.resultsSection.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }

    hideResults() {
        this.resultsSection.style.display = 'none';
        this.resultsSection.classList.remove('fade-in');
    }

    showError(message) {
        this.errorText.textContent = message;
        this.errorMessage.style.display = 'flex';
        
        // Auto-hide error after 5 seconds
        setTimeout(() => {
            this.hideError();
        }, 5000);
    }

    hideError() {
        this.errorMessage.style.display = 'none';
    }
}

// Inicializar la aplicación cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    new PDFSearchApp();
});

// Agregar estilos CSS adicionales para elementos que no están en el HTML inicial
const additionalStyles = `
    .no-results {
        text-align: center;
        padding: 60px 20px;
        color: #6c757d;
    }
    
    .no-results h3 {
        margin-bottom: 10px;
        color: #495057;
    }
    
    .result-item {
        position: relative;
    }
    
    .result-item::after {
        content: 'Clic para abrir';
        position: absolute;
        top: 50%;
        right: 20px;
        transform: translateY(-50%);
        opacity: 0;
        transition: opacity 0.3s ease;
        background: rgba(102, 126, 234, 0.1);
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 0.8rem;
        color: #667eea;
        font-weight: 500;
    }
    
    .result-item:hover::after {
        opacity: 1;
    }
`;

// Inyectar estilos adicionales
const styleSheet = document.createElement('style');
styleSheet.textContent = additionalStyles;
document.head.appendChild(styleSheet);