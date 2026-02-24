# CMI-ESUCAR 2025-2028 · Sistema de Evidencias y Auditoría

## Estructura del proyecto

```
cmi_esucar/
├── app.py              ← Backend Flask (API + autenticación + BD)
├── cmi_esucar.db       ← Base de datos SQLite (se crea automáticamente)
├── requirements.txt    ← Dependencias Python
├── Procfile            ← Para Railway/Render
├── railway.json        ← Configuración Railway
├── uploads/            ← Archivos de evidencia (se crea automáticamente)
└── static/
    ├── index.html      ← CMI interactivo (frontend)
    ├── login.html      ← Pantalla de acceso
    └── escudo.png      ← Escudo institucional
```

---

## OPCIÓN 1 · Despliegue en Railway.app (RECOMENDADO · GRATIS)

### Paso 1 · Crear cuenta
1. Ir a https://railway.app
2. Registrarse con GitHub (necesita cuenta GitHub gratuita)

### Paso 2 · Subir el código a GitHub
1. Crear repositorio nuevo en https://github.com/new
   - Nombre: `cmi-esucar`
   - Privado: ✓ (recomendado)
2. Subir todos los archivos de esta carpeta al repositorio

   **Si tiene Git instalado:**
   ```bash
   cd cmi_esucar
   git init
   git add .
   git commit -m "CMI ESUCAR inicial"
   git branch -M main
   git remote add origin https://github.com/SU_USUARIO/cmi-esucar.git
   git push -u origin main
   ```

   **Si NO tiene Git:** usar la interfaz web de GitHub → "uploading an existing file"

### Paso 3 · Crear proyecto en Railway
1. En Railway → "New Project" → "Deploy from GitHub repo"
2. Seleccionar el repositorio `cmi-esucar`
3. Railway detecta automáticamente Python y el Procfile
4. Agregar variable de entorno:
   - Clic en el servicio → "Variables" → "New Variable"
   - `SECRET_KEY` = `una-clave-secreta-larga-y-aleatoria-2025`
5. El despliegue inicia automáticamente (2-3 minutos)
6. Ir a "Settings" → "Domains" → "Generate Domain"
   → obtendrá una URL como: `cmi-esucar.up.railway.app`

---

## OPCIÓN 2 · Render.com (alternativa gratuita)

1. Ir a https://render.com → "New Web Service"
2. Conectar el repositorio GitHub
3. Configuración:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Environment Variables:** `SECRET_KEY=su-clave-secreta`
4. Plan: Free (suficiente para uso institucional interno)

---

## OPCIÓN 3 · Servidor propio / PC de la institución (intranet)

### Instalar Python (una sola vez)
```bash
# Windows: descargar de https://python.org
# Ubuntu/Debian:
sudo apt update && sudo apt install python3 python3-pip -y
```

### Instalar dependencias
```bash
cd cmi_esucar
pip install -r requirements.txt
```

### Ejecutar el servidor
```bash
# Desarrollo (solo para pruebas):
python app.py

# Producción (para red interna):
gunicorn app:app --bind 0.0.0.0:8080 --workers 2
```

El sistema queda disponible en: `http://IP_DEL_SERVIDOR:8080`
Para conocer la IP: `ipconfig` (Windows) o `hostname -I` (Linux)

---

## Usuarios por defecto

| Usuario   | Contraseña   | Rol          | Acceso                          |
|-----------|--------------|--------------|--------------------------------|
| auditor   | auditor2025  | Auditor OAC  | Todo · valida/rechaza evidencias |
| director  | director2025 | Dirección    | Solo lectura · dashboard        |
| resp_e1   | resp2025     | Responsable  | Eje I (Docencia)               |
| resp_e2   | resp2025     | Responsable  | Eje II (Gestión)               |
| resp_e3   | resp2025     | Responsable  | Eje III (Calidad)              |
| resp_e4   | resp2025     | Responsable  | Eje IV (VcM)                   |
| resp_e5   | resp2025     | Responsable  | Eje V (Innovación)             |

### ⚠️ IMPORTANTE: Cambiar contraseñas antes de usar en producción

Usando la API (con el auditor logueado):
```bash
curl -X PUT https://SU-DOMINIO/api/usuarios/1/password \
  -H "Content-Type: application/json" \
  -d '{"password":"nueva-contraseña-segura"}'
```

O crear nuevos usuarios desde la API:
```bash
curl -X POST https://SU-DOMINIO/api/usuarios \
  -H "Content-Type: application/json" \
  -d '{"username":"jef_estudio","nombre":"Jefatura de Estudio","password":"Clave2025!","rol":"responsable","eje_ids":["E1","E2"]}'
```

---

## Flujo de trabajo del sistema

```
RESPONSABLE                    AUDITOR (OAC)
     │                               │
     ├─ Ve sus tareas por trimestre  │
     ├─ Completa la tarea            │
     ├─ Sube evidencia               │
     │   (descripción + archivo)     │
     │         ──────────────────►   │
     │                               ├─ Recibe notificación visual
     │                               ├─ Revisa evidencia + archivo
     │                               ├─ VALIDA o RECHAZA con obs.
     │         ◄──────────────────   │
     ├─ Si RECHAZADA: corrige        │
     │   y vuelve a enviar           │
     ├─ Si VALIDADA: tarea ✓         │
     │                               │
     └─ KPIs se actualizan           └─ Dashboard siempre al día
        automáticamente
```

---

## API Reference

| Método | Ruta                        | Descripción                    |
|--------|-----------------------------|---------------------------------|
| POST   | /api/login                  | Autenticación                  |
| POST   | /api/logout                 | Cerrar sesión                  |
| GET    | /api/me                     | Usuario actual                 |
| GET    | /api/tareas?year=2025       | Listar estados de tareas       |
| GET    | /api/tareas/{key}           | Detalle tarea + evidencias     |
| POST   | /api/evidencia              | Subir evidencia (multipart)    |
| POST   | /api/auditoria              | Validar o rechazar             |
| GET    | /api/archivo/{uuid}         | Descargar archivo adjunto      |
| GET    | /api/dashboard?year=2025    | Estadísticas y pendientes      |
| GET    | /api/usuarios               | Listar usuarios (auditor)      |
| POST   | /api/usuarios               | Crear usuario (auditor)        |
| PUT    | /api/usuarios/{id}/password | Cambiar contraseña (auditor)   |

---

## Respaldo de datos

La base de datos es el archivo `cmi_esucar.db` y la carpeta `uploads/`.
Para respaldar, copiar ambos a un lugar seguro periódicamente.

En Railway, los datos persisten mientras el proyecto esté activo.
Para mayor seguridad, configurar un volumen persistente en Railway:
Settings → "Volumes" → montar en `/app`

---

## Soporte
Sistema desarrollado para ESUCAR · Plan de Desarrollo Educativo 2025-2028
Oficina de Aseguramiento de la Calidad
