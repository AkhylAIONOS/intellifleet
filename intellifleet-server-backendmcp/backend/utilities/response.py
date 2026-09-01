def clean_llm_response(raw_text: str) -> str:

    if not raw_text:
        return ""

    text = raw_text.replace("\\n", "\n")

    text = text.replace("**", "").replace("`", "").strip()

    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):

            line = line[2:].strip()
            clean_lines.append(line + ".")
        elif line:
            clean_lines.append(line)

    final_clean_text = " ".join(clean_lines)
    return final_clean_text