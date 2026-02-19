// config.js - Comando Central de FruverOS Pro
const CONFIG = {
    // URL de tu backend en Render
    API_URL: "https://fruver-api-gbwr.onrender.com",

    formatearMoneda: (valor) => {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0
        }).format(valor);
    },

    notificar: (titulo, texto, icono = 'success') => {
        Swal.fire({
            title: titulo,
            text: texto,
            icon: icono,
            timer: 2500,
            showConfirmButton: false,
            borderRadius: '1.5rem',
            background: '#ffffff',
            customClass: {
                popup: 'rounded-[2rem] shadow-2xl border border-gray-100',
                title: 'font-black text-gray-800',
                htmlContainer: 'font-bold text-gray-500'
            }
        });
    },

    async solicitar(endpoint, opciones = {}) {
        const token = localStorage.getItem('fruverToken');
        const headersBase = {
            'Authorization': `Bearer ${token}`
        };

        try {
            const respuesta = await fetch(`${this.API_URL}${endpoint}`, {
                ...opciones,
                headers: { ...headersBase, ...opciones.headers }
            });

            if (respuesta.status === 401) {
                localStorage.clear();
                window.location.href = "/static/login.html"; 
                return;
            }

            return respuesta;
        } catch (error) {
            console.error("Error en la petición:", error);
            this.notificar("Error de Conexión", "No se pudo conectar con el servidor", "error");
            throw error;
        }
    }
};

