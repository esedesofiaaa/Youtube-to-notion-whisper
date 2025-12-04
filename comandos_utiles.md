# Gestión de Servicios

# Estado del servicio principal
sudo systemctl status youtube-whisper

# Ver si está activo
sudo systemctl is-active youtube-whisper

# Reiniciar servicio
sudo systemctl restart youtube-whisper

# Detener servicio
sudo systemctl stop youtube-whisper

# Iniciar servicio
sudo systemctl start youtube-whisper

# Ver configuración del servicio
sudo systemctl cat youtube-whisper

# Logs del Sistema

# Logs en tiempo real del servicio
sudo journalctl -u youtube-whisper -f

# Últimas 50 líneas
sudo journalctl -u youtube-whisper -n 50

# Logs de hoy
sudo journalctl -u youtube-whisper --since today

# Logs con rango de tiempo
sudo journalctl -u youtube-whisper --since "2025-12-03 20:00" --until "2025-12-03 22:00"

# Logs de la Aplicación
# Celery worker
tail -f /home/deploy/Youtube-to-notion-whisper/logs/celery_worker.log

# Flower dashboard
tail -f /home/deploy/Youtube-to-notion-whisper/logs/flower.log

# Ver últimas 100 líneas
tail -n 100 /home/deploy/Youtube-to-notion-whisper/logs/celery_worker.log

# Estado de Procesos
# Ver procesos de Python corriendo
ps aux | grep python

# Ver procesos de Celery
ps aux | grep celery

# Ver puertos ocupados
sudo netstat -tlnp | grep -E '8000|5555|6379'

# Ver uso de recursos del servicio
sudo systemctl status youtube-whisper --no-pager -l
Redis (Docker)

# Estado de contenedores
docker ps

# Logs de Redis
docker logs youtube-to-notion-redis

# Entrar a Redis CLI
docker exec -it youtube-to-notion-redis redis-cli

# Ver info de Redis
docker exec -it youtube-to-notion-redis redis-cli INFO

# Tailscale
# Estado de Tailscale
sudo tailscale status

# Ver rutas configuradas
sudo tailscale serve status

# IP de Tailscale del servidor
tailscale ip -4

# Ver logs de Tailscale
sudo journalctl -u tailscaled -f

# Archivos y Configuración
# Ver variables de entorno
cat /home/deploy/Youtube-to-notion-whisper/.env

# Ver estructura de directorios
tree -L 2 /home/deploy/Youtube-to-notion-whisper

# Espacio en disco
df -h

# Uso de disco del proyecto
du -sh /home/deploy/Youtube-to-notion-whisper/*
Scripts Manuales
bash# Detener todo
/home/deploy/Youtube-to-notion-whisper/scripts/stop_all.sh

# Iniciar todo
/home/deploy/Youtube-to-notion-whisper/scripts/start_all.sh

# Verificar salud
curl http://localhost:8000/health
Depuración Rápida
bash# Ver últimos errores del servicio
sudo journalctl -u youtube-whisper -p err -n 20

# Ver uso de memoria
free -h

# Ver procesos que más usan CPU
top -o %CPU | head -20

# Ver conectividad a APIs
curl -I https://api.notion.com/v1/
Estos son los comandos específicos del proyecto en producción.Claude can make mistakes. Please double-check responses.