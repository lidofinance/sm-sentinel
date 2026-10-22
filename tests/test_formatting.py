from sentinel.modules.formatting import Bold, Code, Text, TextLink, block_footer, markdown


def test_plain_text_escapes_every_markdown_v2_special_character():
    assert markdown(r"_*[]()~`>#+-=|{}.!\ ok") == r"\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!\\ ok"


def test_non_string_children_are_rendered_with_str():
    assert markdown("Operator #", 42, " bond ", 1.5) == r"Operator \#42 bond 1\.5"


def test_bold_and_code_wrap_escaped_content():
    assert Bold("v1.2", " (new)").as_markdown() == r"*v1\.2 \(new\)*"
    assert Code("0xab_cd.ef").as_markdown() == r"`0xab\_cd\.ef`"


def test_text_link_escapes_label_and_only_url_delimiters():
    link = TextLink("tx 1.0", url=r"https://etherscan.io/tx/0x1?a=b_c(1)\d")

    assert link.as_markdown() == r"[tx 1\.0](https://etherscan.io/tx/0x1?a=b_c(1\)\\d)"


def test_nested_nodes_render_in_order():
    message = Text(
        Bold("Stake"), " in ", Code("CSM"), Text("!", TextLink("UI", url="https://x.io"))
    )

    assert message.as_markdown() == r"*Stake* in `CSM`\![UI](https://x.io)"


def test_block_footer_renders_first_and_last_block_links():
    footer = block_footer(
        "Node Operator #1",
        [("1", "https://e.io/b/1"), ("2", "https://e.io/b/2"), ("3", "https://e.io/b/3")],
    )

    assert footer.as_markdown() == (
        "\n\nNode Operator \\#1\nBlocks: [1](https://e.io/b/1) \\.\\.\\. [3](https://e.io/b/3)"
    )
