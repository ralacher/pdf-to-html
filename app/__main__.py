"""Allow running the worker as `python -m app` when WORKER_MODE=true."""
import os

if os.environ.get("WORKER_MODE", "false").lower() == "true":
    from app.worker import main
    main()
else:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
