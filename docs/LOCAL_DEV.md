# Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Run tests:

```bash
pytest
```

Clean runtime data:

```bash
rm -f data/jobs/*.json data/outputs/* data/logs/*
```

Runtime data is ignored by git and should not be included in copy-over zips.
