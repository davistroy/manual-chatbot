import pathlib, codecs
hex_data = pathlib.Path("C:/Users/Troy Davis/dev/personal/manual-chatbot/output/script.hex").read_text()
script = codecs.decode(hex_data, "hex").decode("utf-8")
pathlib.Path("C:/Users/Troy Davis/dev/personal/manual-chatbot/output/validate_cj.py").write_text(script, encoding="utf-8")
print(f"Decoded {len(script)} chars")
