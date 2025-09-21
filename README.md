# Multi-Cloud DevOps MCP Server 🚀

Un servidor MCP (Model Context Protocol) que proporciona herramientas para gestionar recursos en múltiples proveedores de nube (AWS, Azure, Hetzner Cloud) y ejecutar comandos SSH remotos.

## 📋 Características

- **AWS**: Ejecución de código boto3 para gestión de recursos AWS
- **Azure**: Gestión de recursos Azure mediante Azure SDK
- **Hetzner Cloud**: Administración de recursos en Hetzner Cloud
- **SSH**: Ejecución remota de comandos SSH
- **Dockerizado**: Fácil despliegue con Docker Compose
- **MCP Compatible**: Integración directa con clientes MCP

## 🛠️ Prerrequisitos

- Docker y Docker Compose instalados
- Cliente MCP compatible (como Cursor IDE)
- Credenciales de los proveedores de nube que planeas usar

## 🚀 Instalación y Configuración

### 1. Configurar Credenciales

Copia el archivo de ejemplo y configura tus credenciales:

```bash
cp local.env .env
```

Edita el archivo `.env` con tus credenciales:

```bash
# ===== AWS Configuration =====
AWS_ACCESS_KEY_ID=tu_access_key_id
AWS_SECRET_ACCESS_KEY=tu_secret_access_key
AWS_DEFAULT_REGION=us-east-1
AWS_PROFILE=tu_perfil_aws  # Opcional

# ===== Azure Configuration =====
AZURE_CLIENT_ID=tu_client_id
AZURE_CLIENT_SECRET=tu_client_secret
AZURE_TENANT_ID=tu_tenant_id
AZURE_SUBSCRIPTION_ID=tu_subscription_id
```

### 2. Construir el Contenedor Docker

```bash
docker compose build
```

### 3. Ejecutar el Servidor

```bash
docker compose up
```

El servidor estará disponible en `http://localhost:8080`

Para ejecutar en segundo plano:

```bash
docker compose up -d
```

### 4. Verificar que el Servidor Funciona

Puedes verificar el estado del servidor visitando:
- Health check: `http://localhost:8080/health`
- MCP endpoint: `http://localhost:8080/mcp`

## 🔧 Integración con Cliente MCP

### Configuración en Cursor IDE

1. Abre la configuración de MCP en Cursor IDE
2. Agrega la siguiente configuración (basada en `cursor_mcp_config.json`):

```json
{
  "mcpServers": {
    "devops-aws": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

### Crear Agente con Prompt Personalizado

Crea un nuevo agente en tu cliente MCP con el siguiente prompt del sistema:

```
DO NOT IMPLEMENT CODE UNLESS I SPECIFY IT. I WANT YOU TO ALWAYS GIVE ME THE OPTIONS TO IMPLEMENT BEFORE MAKING ANY CHANGES TO THE CODE.

Always write code comments in English.

ALWAYS check how a feature is implemented in the code before starting your own, to see if a similar solution exists or to follow the repository's coding style. You are a useful assistant. You have to use "wide_reasoning" before responding to the user's question.

Wide Reasoning
Description: This field is to think in depth about the problem. Think carefully, trying to prevent mistakes. Always analyze the situation, the problem and do self-criticism and planning in the thoughts before saying something or giving a solution.

Points of View
Description: Analyze from multiple expert perspectives, thinking step-by-step. Points of view are a kind of thought that the character is thinking, but they are more specific and are used to analyze situations or possibilities from different unique perspectives and should be used always in these kinds of situations.
Format:

Expert name: "Perspective and reasoning of the expert"
Description: Step-by-step analysis of the problem. Minimum 3 points of view. The experts try to solve the problem in the most detailed and close manner possible, leaving nothing to chance.

Debate
Description: Have the experts from Points of View discuss and argue their perspectives. Experts can think and talk using "disfluencies". THE DEBATE SHOULD ALWAYS BE FOCUSED ON THE MAIN QUESTION, AND EACH CHARACTER SHOULD BE ARGUING OVER THAT. Each character of these points of view characters does a debate with each other to argue talking in a dialog about the situation and what to do or say.
Format:

Expert: "Argument"
Expert: "Counter-argument"

Conclusion
"Final thought content."
Final response to the user's question.
```

## 📚 Herramientas Disponibles

### AWS (boto3_execute_wrapper)
Ejecuta código boto3 para gestionar recursos AWS:
```python
# Ejemplo: Listar buckets S3
import boto3
s3 = boto3.client('s3')
response = s3.list_buckets()
print(response['Buckets'])
```

### Azure (azure_execute_wrapper)
Gestiona recursos Azure:
```python
# Ejemplo: Listar grupos de recursos
from azure.mgmt.resource import ResourceManagementClient
resource_client = ResourceManagementClient(credential, subscription_id)
for rg in resource_client.resource_groups.list():
    print(rg.name)
```

### Hetzner Cloud (hetzner_execute_wrapper)
Administra recursos en Hetzner Cloud:
```python
# Ejemplo: Listar servidores
from hcloud import Client
client = Client(token=hetzner_token)
servers = client.servers.get_all()
for server in servers:
    print(f"{server.name}: {server.status}")
```

### SSH (ssh_execute_wrapper)
Ejecuta comandos remotos via SSH:
```python
# Ejemplo: Ejecutar comando remoto
result = ssh_execute("ls -la /home", "usuario@servidor.com", "password")
print(result)
```

## 🐳 Estructura Docker

El proyecto utiliza Docker Compose con:
- **Puerto**: 8080 (mapeado a localhost:8080)
- **Volúmenes**: 
  - Código fuente montado en `/app`
  - Credenciales AWS desde `~/.aws`
  - Credenciales Azure desde `~/.azure`
- **Red**: `mcp-network` (bridge)

## 🔍 Troubleshooting

### El servidor no inicia
- Verifica que el puerto 8080 no esté en uso
- Revisa los logs: `docker compose logs`
- Asegúrate de que el archivo `.env` existe y tiene las credenciales correctas

### Errores de autenticación
- Verifica que las credenciales en `.env` sean correctas
- Para AWS, asegúrate de que las credenciales tengan los permisos necesarios
- Para Azure, verifica que el Service Principal tenga acceso a la suscripción

### Cliente MCP no se conecta
- Verifica que el servidor esté ejecutándose: `curl http://localhost:8080/health`
- Revisa la configuración del cliente MCP
- Asegúrate de que la URL sea `http://localhost:8080/mcp`

## 📁 Estructura del Proyecto

```
aws_mcp/
├── src/
│   ├── server.py          # Servidor MCP principal
│   ├── providers/         # Proveedores de nube
│   │   ├── aws.py        # Funciones AWS/boto3
│   │   ├── azure.py      # Funciones Azure
│   │   ├── hetzner.py    # Funciones Hetzner Cloud
│   │   └── ssh.py        # Funciones SSH
│   └── utils.py          # Utilidades
├── docker-compose.yml    # Configuración Docker
├── Dockerfile           # Imagen Docker
├── requirements.txt     # Dependencias Python
├── .env                # Credenciales (crear desde local.env)
└── cursor_mcp_config.json # Configuración ejemplo para Cursor
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.