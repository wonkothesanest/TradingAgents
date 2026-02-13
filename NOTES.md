# Ideas
The costs of this tool are high
We would need to do comparisons of input / output of utilizing gpt 5 models vs local models and see what the overall take aways are and if there is much of a difference.

Remove results form the github

How does this fit in our overall workflow?

# HOst setup
Had to install nvidia container toolkit
https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html


# Explanation of flow
 How Celery Works in TradingAgents                                                                                                                                      
                                                                                                                                                                         
  Overview: What is Celery?                                                                                                                                              
                                                                                                                                                                       
  Celery is a distributed task queue system that allows you to run time-consuming tasks in the background. Instead of making users wait for a long analysis to complete, 
  you:                                                                                                                                                                   
  1. Accept the request immediately
  2. Queue the work to run in the background
  3. Let users check back later for results

  Think of it like a restaurant:
  - API = Waiter (takes orders, returns results)
  - Celery Broker (Redis) = Order ticket system (passes orders to kitchen)
  - Celery Worker = Chef (does the actual cooking)
  - Result Backend (Redis) = Pickup counter (stores completed orders)

  ---
  Your System Architecture

  ┌─────────────────────────────────────────────────────────────────┐
  │                        DOCKER NETWORK                            │
  │                                                                   │
  │  ┌──────────────┐         ┌──────────────┐                      │
  │  │   API Node   │         │ Worker Node  │                      │
  │  │ (FastAPI)    │         │  (Celery)    │                      │
  │  │              │         │              │                      │
  │  │ Port: 8123   │         │ Concurrency:2│                      │
  │  └──────┬───────┘         └──────┬───────┘                      │
  │         │                        │                               │
  │         │    ┌──────────────────┴────────────────┐             │
  │         │    │                                    │             │
  │         ▼    ▼                                    ▼             │
  │  ┌──────────────────────┐              ┌──────────────┐        │
  │  │   Redis (Port 6379)  │              │   Ollama     │        │
  │  │                      │              │  (LLM Server)│        │
  │  │ • Celery Broker      │              │              │        │
  │  │ • Result Backend     │              │ Port: 11434  │        │
  │  │ • Job Store          │              └──────────────┘        │
  │  └──────────────────────┘                                       │
  │                                                                   │
  └─────────────────────────────────────────────────────────────────┘

  ---
  What's Running in Each Container

  1. API Container (tradingagents-api)

  Command:
  uvicorn trading_api.main:app --host 0.0.0.0 --port 8000

  What it does:
  - Runs FastAPI web server
  - Accepts HTTP requests from users
  - Creates jobs in Redis JobStore
  - Sends tasks to Celery via Redis broker
  - Returns job IDs immediately (non-blocking)
  - Serves status/result endpoints

  Key endpoints:
  - POST /jobs - Create new analysis job
  - GET /jobs/{job_id} - Check job status
  - GET /jobs/{job_id}/result - Get completed results

  2. Worker Container (tradingagents-worker)

  Command:
  celery -A trading_api.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --time-limit=1800 \
    --soft-time-limit=1500 \
    --max-tasks-per-child=50

  Breaking down the command:
  - -A trading_api.celery_app - Use the Celery app from celery_app.py
  - worker - Run in worker mode (processes tasks)
  - --loglevel=info - Show informational logs
  - --concurrency=2 - Run 2 parallel worker processes
  - --time-limit=1800 - Hard timeout at 30 minutes (kills task)
  - --soft-time-limit=1500 - Soft timeout at 25 minutes (raises exception)
  - --max-tasks-per-child=50 - Restart worker after 50 tasks (prevents memory leaks)

  What it does:
  - Listens to Redis for new tasks
  - Pulls tasks from the queue
  - Executes tradingagents.analyze_stock task
  - Updates job status in Redis JobStore
  - Stores results in Redis JobStore
  - Can run multiple tasks in parallel (concurrency=2)

  3. Redis Container (tradingagents-redis)

  Command:
  redis-server --maxmemory 512mb --maxmemory-policy noeviction

  What it does (3 roles):
  1. Celery Broker - Message queue for task distribution
    - API puts tasks here
    - Workers pull tasks from here
  2. Celery Result Backend - Stores Celery task metadata
    - Task status (pending, started, success, failure)
    - Task return values
  3. JobStore - Your custom job tracking
    - Job metadata (ticker, date, config)
    - Job status (pending, running, completed, failed)
    - Job results (decision, reports, state)

  4. Ollama Container (tradingagents-ollama)

  Command:
  /bin/ollama serve

  What it does:
  - Runs local LLM inference server
  - Provides API compatible with OpenAI format
  - Workers send LLM requests here during analysis

  ---
  Task Flow: What Happens When You Submit a Job

  Let me trace through a complete request:

  ┌─────────┐
  │  USER   │
  └────┬────┘
       │
       │ 1. curl POST /jobs
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ API CONTAINER                                                │
  │                                                               │
  │  trading_api/main.py (FastAPI)                               │
  │  ├─ create_job() endpoint                                    │
  │  │  ├─ store.create_job(ticker, date, config)              │
  │  │  │  └─ Writes to Redis: "tradingagents:job:<uuid>"      │
  │  │  │                                                        │
  │  │  ├─ analyze_stock.delay(job_id, ticker, date, config)   │
  │  │  │  └─ Publishes task to Redis broker                   │
  │  │  │                                                        │
  │  │  └─ Returns job_id to user (202 Accepted)               │
  │  │                                                           │
  └──┼───────────────────────────────────────────────────────────┘
     │
     │ Task message in Redis
     │
     ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ REDIS BROKER                                                 │
  │                                                               │
  │  Queue: celery                                               │
  │  Task: tradingagents.analyze_stock[<task_id>]               │
  │  Args: [job_id, ticker, date, config]                       │
  │                                                               │
  └──┼───────────────────────────────────────────────────────────┘
     │
     │ Worker polls Redis
     │
     ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ WORKER CONTAINER (ForkPoolWorker-1 or ForkPoolWorker-2)     │
  │                                                               │
  │  trading_api/tasks.py                                        │
  │  ├─ @celery_app.task analyze_stock()                        │
  │  │  │                                                        │
  │  │  ├─ store.update_retry_count(job_id, 0)                 │
  │  │  │  └─ Writes to Redis JobStore                         │
  │  │  │                                                        │
  │  │  ├─ store.update_job_status(job_id, RUNNING)            │
  │  │  │  └─ Writes to Redis JobStore                         │
  │  │  │                                                        │
  │  │  ├─ ta = TradingAgentsGraph(config)                     │
  │  │  │  └─ Initialize agents, LLM clients, etc.             │
  │  │  │                                                        │
  │  │  ├─ final_state, decision = ta.propagate(ticker, date)  │
  │  │  │  │                                                     │
  │  │  │  ├─ Analysts run in parallel ─────────┐              │
  │  │  │  │  ├─ Market Analyst      │          │              │
  │  │  │  │  ├─ Sentiment Analyst   │  Calls   │              │
  │  │  │  │  ├─ News Analyst        ├─ Ollama ─┤              │
  │  │  │  │  └─ Fundamentals Analyst│          │              │
  │  │  │  │                          │          │              │
  │  │  │  ├─ Researchers debate ─────┘          │              │
  │  │  │  │  ├─ Bull Researcher                 │              │
  │  │  │  │  └─ Bear Researcher                 │              │
  │  │  │  │                                      ▼              │
  │  │  │  ├─ Trader makes decision      ┌──────────────┐      │
  │  │  │  ├─ Risk Management evaluates  │   OLLAMA     │      │
  │  │  │  └─ Portfolio Manager approves │ LLM Server   │      │
  │  │  │                                 └──────────────┘      │
  │  │  │                                                        │
  │  │  ├─ Write results to filesystem                          │
  │  │  │  └─ /data/results/<ticker>/<date>/                   │
  │  │  │                                                        │
  │  │  ├─ store.set_job_result(job_id, decision, state, ...)  │
  │  │  │  └─ Writes to Redis JobStore                         │
  │  │  │                                                        │
  │  │  └─ store.update_job_status(job_id, COMPLETED)          │
  │  │     └─ Writes to Redis JobStore                         │
  │  │                                                           │
  │  └─ Returns result dict                                     │
  │     └─ Celery stores in result backend                      │
  │                                                               │
  └─────────────────────────────────────────────────────────────┘

  ---
  Data Storage: What's in Redis

  At any given time, Redis contains:

  1. Celery Queue (Broker)

  Key: celery
  Type: List
  Purpose: Task messages waiting to be processed

  Example:
  {
    "task": "tradingagents.analyze_stock",
    "id": "d42590c5-7d2d-4bb8-9290-0c8c5810026d",
    "args": ["dc2c6887-86a0-47f5-8469-423ccadd0aaa", "NVDA", "2026-02-12", {...}]
  }

  2. Celery Results (Result Backend)

  Key: celery-task-meta-<task_id>
  Type: Hash
  Purpose: Celery's internal task tracking

  Example:
  {
    "status": "SUCCESS",
    "result": {...},
    "traceback": null,
    "children": []
  }

  3. Job Store (Your Custom Storage)

  Key: tradingagents:job:<job_id>
  Type: Hash
  Purpose: Job metadata and results for API responses

  Example:
  {
    "job_id": "dc2c6887-86a0-47f5-8469-423ccadd0aaa",
    "ticker": "NVDA",
    "date": "2026-02-12",
    "status": "completed",
    "created_at": "2026-02-13T06:06:32.162409+00:00",
    "started_at": "2026-02-13T06:06:32.178240+00:00",
    "completed_at": "2026-02-13T06:10:45.123456+00:00",
    "result": "{\"decision\": \"BUY\", \"final_state\": {...}, \"reports\": {...}}",
    "retry_count": "0"
  }

  ---
  Key Concepts

  Task vs Job

  - Celery Task = The function being executed (analyze_stock)
  - Job = Your business concept (analyzing a stock on a date)
  - Task ID = Celery's tracking ID
  - Job ID = Your tracking ID

  Why Two IDs?

  # In API main.py:
  job_id = store.create_job(...)  # dc2c6887... (your ID)
  task = analyze_stock.delay(job_id, ...)  # d42590c5... (Celery's ID)

  - Job ID - What you show to users, stored in JobStore
  - Task ID - Celery's internal tracking, stored in result backend

  Concurrency

  --concurrency=2
  The worker runs 2 child processes in parallel:
  - ForkPoolWorker-1 - Can process one task
  - ForkPoolWorker-2 - Can process another task simultaneously

  This means you can analyze 2 different stocks at the same time.

  Timeouts

  --time-limit=1800      # 30 minutes - hard kill
  --soft-time-limit=1500 # 25 minutes - raises exception

  If a task takes too long:
  1. At 25 minutes: SoftTimeLimitExceeded exception raised
    - Task can catch this and cleanup gracefully
  2. At 30 minutes: Worker process is killed immediately
    - No cleanup, just terminated

  ---
  Current Configuration

  From tradingagents/default_config.py:

  "celery_broker_url": "redis://redis:6379/0"          # Where tasks are queued
  "celery_result_backend": "redis://redis:6379/0"      # Where results are stored
  "celery_task_time_limit": 1800                        # 30 min hard timeout
  "celery_task_soft_time_limit": 1500                   # 25 min soft timeout
  "celery_worker_prefetch_multiplier": 4                # Prefetch 4 tasks per worker
  "celery_result_expires": 3600                         # Results expire after 1 hour
  "celery_task_serializer": "json"                      # Serialize tasks as JSON
  "celery_result_serializer": "json"                    # Serialize results as JSON
  "celery_accept_content": ["json"]                     # Only accept JSON

  ---
  Why This Architecture?

  Without Celery (Synchronous):
  User → API → Wait 10+ minutes → Response
          (API blocked, can't serve other requests)

  With Celery (Asynchronous):
  User → API → Immediate response with job_id
         Worker → Process in background (10+ minutes)
  User → API → Poll for status/results

  Benefits:
  1. Non-blocking - API responds instantly
  2. Scalable - Add more workers to process more jobs
  3. Fault tolerant - If worker crashes, task can be retried
  4. Resource isolation - Heavy LLM work doesn't slow down API
  5. Parallel processing - Multiple stocks analyzed simultaneously

  ---