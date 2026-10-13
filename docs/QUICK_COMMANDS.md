# 🚀 Guia Rápido de Comandos - ClipBuilder

Referência rápida dos comandos mais úteis para trabalhar com o ClipBuilder.

---

## 📦 Docker Compose

### Iniciar a aplicação

```bash
# Iniciar todos os serviços
docker compose up -d

# Iniciar e forçar rebuild
docker compose up -d --build

# Iniciar e acompanhar logs
docker compose up
```

### Parar a aplicação

```bash
# Parar todos os serviços
docker compose down

# Parar e remover volumes (⚠️ apaga dados)
docker compose down -v

# Parar e remover tudo (imagens, volumes, redes)
docker compose down -v --rmi all
```

### Logs e monitoramento

```bash
# Ver logs de todos os serviços
docker compose logs

# Acompanhar logs em tempo real
docker compose logs -f

# Ver logs de um serviço específico
docker compose logs backend
docker compose logs frontend
docker compose logs db

# Ver últimas 100 linhas
docker compose logs --tail=100

# Ver logs com timestamp
docker compose logs -f --timestamps
```

### Reiniciar serviços

```bash
# Reiniciar todos os serviços
docker compose restart

# Reiniciar um serviço específico
docker compose restart backend
docker compose restart frontend
docker compose restart db

# Reconstruir e reiniciar
docker compose up -d --build --force-recreate
```

### Status e informações

```bash
# Ver status dos containers
docker compose ps

# Ver uso de recursos
docker stats

# Ver uso de disco
docker system df

# Inspecionar um serviço
docker compose exec backend env
```

---

## 🐚 Acesso aos Containers

### Backend (Python/FastAPI)

```bash
# Abrir shell no container do backend
docker compose exec backend bash

# Executar comando específico
docker compose exec backend python -c "print('Hello')"

# Ver variáveis de ambiente
docker compose exec backend env

# Listar arquivos de dados
docker compose exec backend ls -lah /app/data

# Ver logs da aplicação
docker compose exec backend tail -f /app/logs/app.log
```

### Frontend (React/Vite)

```bash
# Abrir shell no container do frontend
docker compose exec frontend sh

# Ver configuração do Nginx
docker compose exec frontend cat /etc/nginx/nginx.conf
```

### Banco de Dados (PostgreSQL)

```bash
# Abrir shell no container do banco
docker compose exec db bash

# Conectar ao PostgreSQL via psql
docker compose exec db psql -U clipbuilder -d clipbuilder

# Fazer backup do banco
docker compose exec db pg_dump -U clipbuilder clipbuilder > backup.sql

# Restaurar backup
docker compose exec -T db psql -U clipbuilder clipbuilder < backup.sql
```

---

## 🗄️ Comandos PostgreSQL

### Dentro do psql (após `docker compose exec db psql -U clipbuilder -d clipbuilder`)

```sql
-- Listar todas as tabelas
\dt

-- Descrever estrutura de uma tabela
\d users
\d videos
\d tutorials

-- Ver usuários cadastrados
SELECT id, email, role, created_at FROM users;

-- Ver vídeos cadastrados
SELECT id, title, filename, created_at FROM videos;

-- Ver contagem de registros
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM videos;

-- Limpar tabela (cuidado!)
TRUNCATE TABLE videos CASCADE;

-- Sair do psql
\q
```

---

## 🔧 Manutenção e Limpeza

### Limpar recursos Docker

```bash
# Limpar containers parados
docker container prune -f

# Limpar imagens não utilizadas
docker image prune -a -f

# Limpar volumes não utilizados (⚠️ cuidado com dados)
docker volume prune -f

# Limpar tudo de uma vez
docker system prune -a -f --volumes

# Ver espaço ocupado
docker system df -v
```

### Resetar aplicação completamente

```bash
# ⚠️ ATENÇÃO: Isso apaga TODOS os dados!
docker compose down -v
docker volume rm clipbuilder_postgres_data clipbuilder_backend_data clipbuilder_backend_logs
docker system prune -a -f
docker compose up -d --build
```

### Backup e restauração

```bash
# Backup do banco de dados
docker compose exec db pg_dump -U clipbuilder clipbuilder > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup dos dados (vídeos, imagens)
docker compose exec backend tar -czf - /app/data > data_backup_$(date +%Y%m%d_%H%M%S).tar.gz

# Restaurar banco de dados
docker compose exec -T db psql -U clipbuilder clipbuilder < backup.sql

# Restaurar dados
cat data_backup.tar.gz | docker compose exec -T backend tar -xzf - -C /
```

---

## 🐛 Debug e Troubleshooting

### Verificar conectividade

```bash
# Testar conexão do backend com o banco
docker compose exec backend python -c "from sqlalchemy import create_engine; import os; engine = create_engine(os.getenv('DATABASE_URL')); conn = engine.connect(); print('✅ Conexão OK'); conn.close()"

# Testar porta do frontend
curl http://localhost

# Testar API do backend
curl http://localhost:8000/health

# Testar API docs
curl http://localhost:8000/docs
```

### Verificar configurações

```bash
# Ver variáveis de ambiente do backend
docker compose exec backend env | grep CLERK
docker compose exec backend env | grep DATABASE
docker compose exec backend env | grep ADMIN

# Ver variáveis do frontend
docker compose exec frontend env | grep VITE

# Ver portas expostas
docker compose ps
netstat -tulpn | grep LISTEN
```

### Verificar logs de erro

```bash
# Filtrar apenas erros
docker compose logs backend | grep ERROR
docker compose logs backend | grep Exception
docker compose logs backend | grep Traceback

# Últimos erros
docker compose logs --tail=100 backend | grep -i error
```

### Testes de API

```bash
# Health check
curl http://localhost:8000/health

# Teste de autenticação (substitua TOKEN)
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/videos

# Upload de arquivo de teste
curl -X POST -F "file=@video.mp4" http://localhost:8000/api/upload
```

---

## 🔐 Segurança e Permissões

### Verificar permissões de arquivos

```bash
# Ver permissões dos diretórios de dados
docker compose exec backend ls -la /app/data
docker compose exec backend ls -la /app/logs

# Corrigir permissões (se necessário)
docker compose exec backend chown -R app:app /app/data
docker compose exec backend chmod -R 755 /app/data
```

### Gerar senhas seguras

```bash
# Gerar senha aleatória forte
openssl rand -base64 32

# Gerar senha hexadecimal
openssl rand -hex 32

# Gerar UUID
uuidgen
```

---

## 📊 Monitoramento

### Uso de recursos

```bash
# Monitorar uso de CPU/RAM em tempo real
docker stats

# Ver processos dentro do container
docker compose exec backend ps aux
docker compose top backend

# Ver espaço em disco
df -h
docker system df
```

### Performance

```bash
# Tempo de resposta da API
time curl http://localhost:8000/health

# Testar carga (requer apache-bench)
ab -n 100 -c 10 http://localhost:8000/health

# Monitorar logs em tempo real
watch -n 1 'docker compose logs --tail=20 backend'
```

---

## 🔄 Git e Versionamento

### Comandos úteis

```bash
# Clone do repositório
git clone https://github.com/Eduhs21/ClipBuilder.git
cd ClipBuilder

# Atualizar para última versão
git pull origin main

# Ver status
git status

# Criar branch para feature
git checkout -b feature/minha-feature

# Commit e push
git add .
git commit -m "feat: adiciona nova funcionalidade"
git push origin feature/minha-feature

# Voltar para main e atualizar
git checkout main
git pull origin main
```

---

## 🧪 Desenvolvimento

### Modo desenvolvimento (sem Docker)

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (em outro terminal)
cd frontend
npm install
npm run dev
```

### Atualizar dependências

```bash
# Backend
docker compose exec backend pip install --upgrade -r requirements.txt

# Frontend (reconstruir)
docker compose up -d --build frontend
```

### Executar testes

```bash
# Backend (quando implementado)
docker compose exec backend pytest

# Verificar sintaxe Python
docker compose exec backend python -m py_compile main.py
```

---

## 📚 Referências Rápidas

### Portas padrão

- **Frontend:** `http://localhost` (porta 80)
- **Backend API:** `http://localhost:8000`
- **API Docs:** `http://localhost:8000/docs`
- **Admin Panel:** `http://localhost/admin`
- **PostgreSQL:** `localhost:5432` (apenas internamente)

### Diretórios importantes

- `/app/data` - Vídeos e imagens (dentro do container backend)
- `/app/logs` - Logs da aplicação (dentro do container backend)
- `/var/lib/postgresql/data` - Dados do PostgreSQL (dentro do container db)

### Variáveis obrigatórias

```env
DB_PASSWORD=...
VITE_CLERK_PUBLISHABLE_KEY=...
ADMIN_EMAIL=...
ADMIN_PASSWORD=...
CLERK_SECRET_KEY=...
CLERK_WEBHOOK_SECRET=...
```

---

## 🆘 Comandos de Emergência

### Aplicação não responde

```bash
docker compose restart
docker compose logs -f
```

### Banco de dados travado

```bash
docker compose restart db
docker compose exec db psql -U clipbuilder -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'clipbuilder' AND pid <> pg_backend_pid();"
```

### Espaço em disco cheio

```bash
docker system prune -a -f --volumes
du -sh /var/lib/docker
```

### Reset total (último recurso)

```bash
docker compose down -v
docker system prune -a -f --volumes
rm -rf backend/__pycache__
rm -rf backend/.venv
docker compose up -d --build
```

---

## 💡 Dicas Profissionais

1. **Sempre faça backup antes de operações destrutivas**
   ```bash
   docker compose exec db pg_dump -U clipbuilder clipbuilder > backup.sql
   ```

2. **Use aliases para comandos frequentes**
   ```bash
   alias dcup='docker compose up -d'
   alias dcdown='docker compose down'
   alias dclogs='docker compose logs -f'
   alias dcps='docker compose ps'
   ```

3. **Monitore logs regularmente**
   ```bash
   docker compose logs -f --tail=100
   ```

4. **Verifique o tamanho dos volumes periodicamente**
   ```bash
   docker system df -v
   ```

5. **Mantenha os containers atualizados**
   ```bash
   docker compose pull
   docker compose up -d --build
   ```

---

**📖 Mais informações:** Consulte o [README.md](../README.md) para documentação completa.

**🐛 Problemas?** Veja [Solução de Problemas](../README.md#-solução-de-problemas) ou [abra uma issue](https://github.com/Eduhs21/ClipBuilder/issues).