Manual scripts that talk to a RUNNING backend on localhost:8000 (they are not
tests and are excluded from pytest). `post_sample_transaction.py` writes to
whatever database that server uses — never point it at your real data.
