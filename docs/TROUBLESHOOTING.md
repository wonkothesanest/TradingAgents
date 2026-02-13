# Troubleshooting Guide

## Common Issues

### API Returns 503 Service Unavailable

**Cause:** Redis not running or not accessible

**Fix:**
```bash
docker-compose ps redis  # Check status
docker-compose logs redis  # Check logs
docker-compose restart redis
```

### Job Stuck in "pending" Status

**Cause:** Worker not running or crashed

**Fix:**
```bash
docker-compose ps worker  # Check status
docker-compose logs worker  # Check for errors
docker-compose restart worker
```

**Verify queue:**
```bash
docker exec -it tradingagents-redis-1 redis-cli LLEN celery
# Should show pending jobs count
```

### Job Failed: "LLM service unavailable"

**Cause:** Ollama not running or out of memory

**Fix:**
```bash
docker-compose ps ollama
nvidia-smi  # Check GPU memory
docker-compose logs ollama

# Restart Ollama
docker-compose restart ollama
```

### Result Endpoint Returns 404

**Cause:** Results not persisted or volume not mounted

**Fix:**
```bash
# Check volume exists
docker volume ls | grep results

# Inspect volume
docker volume inspect tradingagents_results_data

# Check results directory
docker run --rm -v tradingagents_results_data:/data alpine ls -lah /data/results
```

### Docker Compose Fails to Start

**Cause:** Port conflicts or GPU not available

**Fix:**
```bash
# Check port availability
sudo lsof -i :8000
sudo lsof -i :6379
sudo lsof -i :11434

# Check GPU
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Job Times Out After 30 Minutes

**Expected behavior** if analysis takes too long.

**Fix (increase timeout):**

Edit `trading_api/celery_app.py`:
```python
celery_app.conf.task_time_limit = 3600  # 60 minutes
celery_app.conf.task_soft_time_limit = 3300  # 55 minutes
```

Rebuild and restart:
```bash
docker-compose down
docker-compose build worker
docker-compose up -d
```

### High Memory Usage

**Cause:** Multiple concurrent jobs with large models

**Fix:**
1. Reduce worker concurrency:
   ```yaml
   worker:
     command: celery ... --concurrency=1
   ```

2. Use smaller model in config:
   ```json
   {
     "llm_provider": "ollama",
     "deep_think_llm": "qwen3:8b"
   }
   ```

## Debugging Tips

### Enable Debug Logging

Edit `docker-compose.yml`:
```yaml
worker:
  environment:
    - LOG_LEVEL=DEBUG
```

### Access Worker Shell

```bash
docker exec -it tradingagents-worker-1 bash
```

### Inspect Celery Tasks

```bash
docker exec -it tradingagents-worker-1 celery -A trading_api.celery_app inspect active
docker exec -it tradingagents-worker-1 celery -A trading_api.celery_app inspect stats
```

### Check API Logs

```bash
docker-compose logs -f api --tail=100
```

## Getting Help

1. Check GitHub issues: https://github.com/your-org/TradingAgents/issues
2. Enable debug logging and capture full error
3. Include docker-compose.yml and .env (redact secrets)
4. Provide `docker-compose logs` output
