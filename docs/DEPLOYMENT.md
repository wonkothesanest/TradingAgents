# Deployment Guide

## Prerequisites

- Docker Engine 24.0+ with Docker Compose plugin
- NVIDIA GPU with CUDA support (for Ollama)
- nvidia-container-toolkit installed
- 50GB free disk space (models + cache)
- Ports available: 8000 (API), 6379 (Redis), 11434 (Ollama)

## Quick Start

1. **Clone repository:**
   ```bash
   git clone https://github.com/your-org/TradingAgents.git
   cd TradingAgents
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and set required API keys
   ```

3. **Start services:**
   ```bash
   docker-compose up -d
   ```

4. **Verify health:**
   ```bash
   curl http://localhost:8000/health
   ```

5. **Submit test job:**
   ```bash
   curl -X POST http://localhost:8000/jobs \
     -H "Content-Type: application/json" \
     -d '{"ticker": "NVDA", "date": "2024-05-10"}'
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | redis://redis:6379/0 | Redis connection URL |
| `CELERY_BROKER_URL` | Yes | redis://redis:6379/0 | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Yes | redis://redis:6379/0 | Celery result backend |
| `OLLAMA_BASE_URL` | No | http://ollama:11434 | Ollama service URL |
| `RESULTS_DIR` | No | /data/results | Results storage path |
| `OPENAI_API_KEY` | No* | - | OpenAI API key (* if using openai) |

### Concurrency

Edit `docker-compose.yml` worker service:
```yaml
worker:
  command: celery -A trading_api.celery_app worker --concurrency=2
  #                                                             ↑
  #                                            Adjust based on GPU memory
```

## Production Considerations

1. **Reverse Proxy:** Use nginx/traefik for SSL and rate limiting
2. **Monitoring:** Add Prometheus + Grafana for metrics
3. **Log Aggregation:** Ship logs to ELK or Loki
4. **Backup:** Regularly backup `/data/results` volume
5. **Security:** Run API behind firewall, use API keys

## Scaling

**Vertical (single machine):**
- Increase worker concurrency based on GPU memory
- Add more Redis memory if queues grow large

**Horizontal (multi-machine):**
- Deploy workers on separate GPU machines
- Use shared Redis instance
- Use S3/NFS for shared results storage

## Monitoring

**Container health:**
```bash
docker-compose ps
docker-compose logs -f worker
```

**Queue status:**
```bash
docker exec -it tradingagents-redis-1 redis-cli
> LLEN celery
> KEYS celery*
```

**GPU utilization:**
```bash
nvidia-smi -l 1
```

## Updates

```bash
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```
