## Env vars

These env vars can be set and influence how refget works

    INDEXDBPATH - Path to index DB file
    SEQPATH - Path to directory with sequence data
    DEBUG - If set, the log level is DEBUG
    LOGLEVEL - These are Python log levels. "DEBUG, "INFO" and "ERROR" are used in refget
    MOUNTPATH - URL path where the API is mounted, e.g. "/api/refget"

## Reconfigure at runtime

The app will read a file named .env and source the variables from there.
If the integrated web server, uvicorn, is started with 2 or more workers, you
can send a SIGHUP to the managing process and it will gracefully restart the
workers and apply the new config.

### Run tests and linting
    Tests:
    pytest
    
    Indent:
    ruff format src/refget
    
    Lint:
    ruff check src/refget
    
    Type check:
    MYPYPATH=src/stubs/ python -m mypy src/refget/
