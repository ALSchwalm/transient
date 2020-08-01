How to Embed Files Into Markdown Documents
------------------------------------------

Add the replacement field `{EMBED_FILE_HERE}` into the markdown template.

This field will be replaced with the embedded file when using:

```bash
scripts/embed_file_into_markdown_template.py \
    --file-to-embed path/to/file/to/embed \
    --markdown-template path/to/markdown/template \
    --output-file path/to/output/file
```

