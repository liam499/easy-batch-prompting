"""The HTML viewer renders self-contained, injection-safe reports."""
import json

import aieasybatch as ab
from aieasybatch import cli
from aieasybatch.viewer import render_html


def test_render_embeds_data_and_is_injection_safe():
    recs = [{"prompt": "p", "prompt_id": "0", "provider": "mock", "model": "x",
             "custom_id": "c", "output": "danger </script> here", "error": None,
             "usage": {"total_tokens": 3}, "cost_usd": None, "latency_ms": 1}]
    html = render_html(recs)
    assert "__AEB_DATA__" not in html              # placeholder was filled
    assert "</script> here" not in html            # the raw close-tag must be escaped
    assert "<\\/script>" in html                   # ...as <\/script>
    # the embedded JSON round-trips back to the records
    blob = html.split('id="aeb-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(blob.replace("<\\/", "</"))[0]["output"] == "danger </script> here"


def test_view_cli_writes_report(tmp_path):
    run = tmp_path / "r.jsonl"
    ab.run(prompts=["a", "b"], models=["mock:x", "mock:y"], out=str(run))
    report = tmp_path / "r.html"
    rc = cli.main(["view", str(run), "-o", str(report)])
    assert rc == 0
    text = report.read_text()
    assert report.stat().st_size > 2000
    assert "prompts × models" in text                      # the static template
    assert '"provider": "mock"' in text                    # the run data is embedded
    assert '"model": "x"' in text and '"model": "y"' in text
