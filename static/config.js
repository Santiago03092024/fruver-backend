// config.js - Comando Central de FruverOS Pro (Versión 4.0)
const CONFIG = {
    // CORRECCIÓN: Tu servidor real en Render
    API_URL: "https://fruver-api-gbwr.onrender.com",

    // 1. Formateador de Moneda
    formatearMoneda: (valor) => {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0
        }).format(valor);
    },

    // 2. Motor de Notificaciones
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

    // 3. Peticiones Pro (Fetch con Seguridad)
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

            // Si la sesión expiró (401)
            if (respuesta.status === 401) {
                localStorage.clear();
                // CORRECCIÓN: Ruta completa para evitar el Not Found
                window.location.href = "/static/login.html";
                return;
            }

            return respuesta;
        } catch (error) {
            console.error("Error en la petición:", error);
            this.notificar("Error de Conexión", "No se pudo contactar con el servidor", "error");
            throw error;
        }
    }
};
