# bioflow-py

Official Python SDK for the [BioFlow](https://getbioflow.com) public API.

```bash
pip install bioflow-py
```

```python
from bioflow_py import BioFlow

with BioFlow(api_key="bf_live_…") as bioflow:
    for page in bioflow.pages.list():
        print(page["slug"])
```

Full documentation: <https://getbioflow.com/docs/api/reference>
