# 🚀 Checklist de Deploy em Produção - ClipBuilder

Guia completo para fazer deploy do ClipBuilder em ambiente de produção de forma segura e profissional.

---

## ⚠️ Antes de Começar

**Este guia assume que você está fazendo deploy em:**
- Servidor Linux (Ubuntu 20.04+ ou Debian 11+)
- Docker e Docker Compose instalados
- Domínio próprio configurado (ex: `clipbuilder.com`)
- Acesso SSH ao servidor

---

## 📋 Checklist Pré-Deploy

### ☑️ Infraestrutura

- [ ] Servidor com recursos adequados (mínimo: 4GB RAM, 2 CPUs, 50GB disco)
- [ ] Domínio registrado e DNS configurado
- [ ] Certificado SSL/HTTPS configurado (Let's Encrypt recomendado)
- [ ] Firewall configurado (portas 80, 443, 22)
- [ ] Backup automático configurado
- [ ] Monitoramento configurado (opcional: Prometheus, Grafana)

### ☑️ Contas e Serviços

- [ ] Conta Clerk criada (plano adequado ao volume esperado)
- [ ] Aplicação Clerk configurada para produção
- [ ] Chaves de API obtidas:
  - [ ] Google Gemini (se usar análise de vídeo)
  - [ ]  (se usar Llama/Whisper)
- [ ] Mercado Pago configurado (se usar pagamentos)
- [ ] Servidor SMTP configurado (SendGrid, Mailgun, etc.)

### ☑️ Repositório

- [ ] Código-fonte versionado no Git
- [ ] Branch `main` estável e testada
- [ ] Secrets e `.env` no `.gitignore`
- [ ] README.md atualizado
- [ ] Licença definida

---

## 🔒 Configuração de Segurança

### 1. Variáveis de Ambiente

**Criar `.env` na raiz do projeto:**

```env
# === PRODUÇÃO - NÃO COMMITAR ===

# Banco de dados (SENHA FORTE!)
DB_PASSWORD=SenhaSegura123!@#ComMaisde20Caracteres

# Clerk (CHAVES LIVE!)
VITE_CLERK_PUBLISHABLE_KEY=pk_live_Y0URK3Y...

# Administrador (SENHA FORTE!)
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=SenhaAdminMuitoSegura123!@#

# Mercado Pago (chave real)
VITE_MP_PUBLIC_KEY=APP_USR-real-key-here

# Limites de produção
CLIPBUILDER_MAX_VIDEO_BYTES=10737418240  # 10GB
CLIPBUILDER_GEMINI_MODEL=models/gemini-2.0-flash
```

**Criar `backend/.env`:**

```env
# === BACKEND PRODUÇÃO ===

# Clerk (CHAVES LIVE!)
CLERK_SECRET_KEY=sk_live_Y0URK3Y...
CLERK_WEBHOOK_SECRET=whsec_Y0URW3BH00K...

# SMTP (Serviço profissional)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=SG.sua_api_key_aqui
SMTP_FROM_EMAIL=noreply@seudominio.com

# Segurança
SECRET_KEY=chave_aleatoria_de_64_caracteres_gerada_com_openssl_rand_hex_32
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# CORS (domínios permitidos)
CORS_ORIGINS=https://seudominio.com,https://www.seudominio.com

# Logs
LOG_LEVEL=WARNING
DEBUG=false
```

### 2. Gerar Senhas Seguras

```bash
# Senha do banco de dados
openssl rand -base64 32

# Secret key para JWT
openssl rand -hex 32

# Senha de admin
openssl rand -base64 24
```

### 3. Permissões de Arquivos

```bash
# Proteger arquivos .env
chmod 600 .env
chmod 600 backend/.env

# Verificar
ls -la .env backend/.env
```

---

## 🌐 Configuração de Domínio e SSL

### 1. DNS

Configure os registros DNS:

```
Tipo    Nome    Valor               TTL
A       @       SEU_IP_SERVIDOR     3600
A       www     SEU_IP_SERVIDOR     3600
CNAME   api     seudominio.com      3600
```

### 2. Nginx Reverso Proxy com SSL

**Instalar Certbot:**

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

**Configurar Nginx (`/etc/nginx/sites-available/clipbuilder`):**

```nginx
# Redirecionar HTTP para HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name seudominio.com www.seudominio.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name seudominio.com www.seudominio.com;
    
    # SSL
    ssl_certificate /etc/letsencrypt/live/seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seudominio.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Segurança
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Limites
    client_max_body_size 10G;
    client_body_timeout 300s;
    
    # Frontend
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

**Obter certificado SSL:**

```bash
sudo certbot --nginx -d seudominio.com -d www.seudominio.com
```

**Renovação automática:**

```bash
sudo certbot renew --dry-run
sudo systemctl enable certbot.timer
```

### 3. Atualizar docker-compose.yml

```yaml
services:
  frontend:
    ports:
      - "8080:80"  # Porta interna, Nginx reverso escuta em 80/443
    environment:
      - VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
      - VITE_MP_PUBLIC_KEY=${VITE_MP_PUBLIC_KEY}
    restart: unless-stopped

  backend:
    ports:
      - "8000:8000"  # Apenas localhost
    restart: unless-stopped
    
  db:
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # Backup diário
    labels:
      - "backup.enable=true"
```

---

## 🚀 Deploy

### 1. Preparar Servidor

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo apt install docker-compose-plugin

# Relogar para aplicar grupo docker
exit
# (Fazer login novamente via SSH)
```

### 2. Clonar Repositório

```bash
cd /opt
sudo git clone https://github.com/Eduhs21/ClipBuilder.git
sudo chown -R $USER:$USER ClipBuilder
cd ClipBuilder
```

### 3. Configurar Variáveis

```bash
# Copiar exemplos
cp .env.example .env
cp backend/.env.example backend/.env

# Editar com valores reais
nano .env
nano backend/.env
```

### 4. Build e Deploy

```bash
# Fazer build
docker compose build

# Subir aplicação
docker compose up -d

# Verificar logs
docker compose logs -f

# Verificar status
docker compose ps
```

### 5. Configurar Clerk Webhooks

No [Clerk Dashboard](https://dashboard.clerk.com/):

1. Vá em **Webhooks** → **Add Endpoint**
2. URL: `https://seudominio.com/api/webhook/clerk`
3. Eventos: Selecione todos os eventos de `user.*`
4. Copie o **Signing Secret** e adicione em `backend/.env`:
   ```env
   CLERK_WEBHOOK_SECRET=whsec_...
   ```
5. Reinicie o backend:
   ```bash
   docker compose restart backend
   ```

---

## 🔍 Verificação Pós-Deploy

### ☑️ Checklist de Testes

- [ ] Frontend carrega: `https://seudominio.com`
- [ ] HTTPS funcionando (cadeado verde)
- [ ] API responde: `https://seudominio.com/api/health`
- [ ] Login via Clerk funciona
- [ ] Upload de vídeo funciona
- [ ] Análise de IA funciona (se configurada)
- [ ] Exportação funciona (DOCX, PDF)
- [ ] Painel admin acessível
- [ ] Emails sendo enviados (se SMTP configurado)
- [ ] Logs sem erros críticos

### 🧪 Testes de Carga

```bash
# Testar endpoint de saúde
curl https://seudominio.com/api/health

# Testar performance
ab -n 100 -c 10 https://seudominio.com/

# Monitorar recursos
docker stats
```

---

## 📊 Monitoramento

### 1. Logs Centralizados

```bash
# Ver logs em tempo real
docker compose logs -f

# Salvar logs em arquivo
docker compose logs > logs_$(date +%Y%m%d).txt

# Rotação de logs (adicionar ao crontab)
0 0 * * * docker compose logs --tail=10000 > /var/log/clipbuilder/app_$(date +\%Y\%m\%d).log
```

### 2. Alertas

Configure alertas para:
- [ ] Uso de disco > 80%
- [ ] Uso de RAM > 90%
- [ ] Containers down
- [ ] Erros 500 na API
- [ ] Certificado SSL próximo de expirar

### 3. Monitoramento com Prometheus (Opcional)

Adicionar ao `docker-compose.yml`:

```yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped
```

---

## 💾 Backup e Recovery

### 1. Backup Automático

**Script de backup (`/opt/scripts/backup_clipbuilder.sh`):**

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/clipbuilder"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup do banco
docker compose exec -T db pg_dump -U clipbuilder clipbuilder | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup dos dados
docker compose exec -T backend tar -czf - /app/data > $BACKUP_DIR/data_$DATE.tar.gz

# Manter apenas últimos 7 dias
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup concluído: $DATE"
```

**Automatizar com cron:**

```bash
chmod +x /opt/scripts/backup_clipbuilder.sh

# Adicionar ao crontab
crontab -e

# Backup diário às 2h da manhã
0 2 * * * /opt/scripts/backup_clipbuilder.sh >> /var/log/clipbuilder_backup.log 2>&1
```

### 2. Recovery

```bash
# Restaurar banco de dados
gunzip -c db_20240115_020000.sql.gz | docker compose exec -T db psql -U clipbuilder clipbuilder

# Restaurar dados
cat data_20240115_020000.tar.gz | docker compose exec -T backend tar -xzf - -C /
```

---

## 🔧 Manutenção

### Atualizações

```bash
# Fazer backup primeiro!
/opt/scripts/backup_clipbuilder.sh

# Atualizar código
git pull origin main

# Reconstruir e reiniciar
docker compose down
docker compose up -d --build

# Verificar logs
docker compose logs -f
```

### Limpeza

```bash
# Limpar logs antigos
find /var/log/clipbuilder -name "*.log" -mtime +30 -delete

# Limpar imagens Docker antigas
docker image prune -a -f

# Limpar containers parados
docker container prune -f
```

---

## 🆘 Troubleshooting Produção

### Aplicação não responde

```bash
# Verificar containers
docker compose ps

# Reiniciar serviços
docker compose restart

# Ver logs de erro
docker compose logs backend | grep ERROR
```

### Alto uso de memória

```bash
# Ver uso de recursos
docker stats

# Limitar memória no docker-compose.yml
services:
  backend:
    mem_limit: 2g
    mem_reservation: 1g
```

### Banco de dados lento

```bash
# Conectar ao PostgreSQL
docker compose exec db psql -U clipbuilder

# Verificar consultas lentas
SELECT * FROM pg_stat_activity WHERE state = 'active';

# Reindexar
REINDEX DATABASE clipbuilder;
```

---

## 📈 Otimizações de Performance

### 1. Nginx Caching

```nginx
# Adicionar ao bloco server
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### 2. PostgreSQL Tuning

```sql
-- Otimizações básicas (ajustar conforme recursos do servidor)
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET effective_cache_size = '3GB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
```

### 3. Limites de Upload

Ajustar no Nginx:

```nginx
client_max_body_size 10G;
client_body_buffer_size 10M;
```

---

## ✅ Checklist Final

- [ ] Todas as variáveis de ambiente configuradas
- [ ] SSL/HTTPS funcionando
- [ ] Firewall configurado
- [ ] Backup automático funcionando
- [ ] Monitoramento ativo
- [ ] Logs sendo coletados
- [ ] Performance testada
- [ ] Segurança validada
- [ ] Documentação atualizada
- [ ] Equipe treinada

---

## 📞 Suporte

**Em caso de problemas:**

1. Verificar logs: `docker compose logs -f`
2. Consultar documentação: [README.md](../README.md)
3. Abrir issue: [GitHub Issues](https://github.com/Eduhs21/ClipBuilder/issues)

---

**🎉 Parabéns! Seu ClipBuilder está em produção!**

**Desenvolvido com ❤️ por Eduardo**