"""Pure text helpers for assembling captured dialogue - no emulator, no deps.

Kept separate from navigation.py (which imports perception -> numpy) so the string
logic unit-tests with nothing installed, and the fast CI stays dependency-free.
"""


def merge_dialog(fragments) -> str:
    """Assemble typewriter-captured dialogue fragments into clean, readable text.

    GB Studio renders dialogue character-by-character and pages it, so successive
    captures overlap: a page's tail re-appears at the head of the next capture,
    often with the boundary word truncated ('...you were havin' then 'you were
    having...'), and a word doubles at a page break ('I should' + 'should read'
    -> 'should should'). Left unmerged these produce facts like 'you can you can
    save'. This removes the overlap so a fact reads as it does on screen.
    """
    # 1. Drop fragments wholly contained at the start of a longer one (a partial
    #    render captured before the typewriter finished the line).
    frags = [f for f in fragments
             if f.strip() and not any(o != f and o.startswith(f) for o in fragments)]
    words: list[str] = []
    for f in frags:
        fw = f.split()
        # 2. Largest word-overlap between the tail of `words` and the head of `fw`,
        #    allowing the last existing word to be a truncated prefix of fw's word.
        best = 0
        for k in range(1, min(len(words), len(fw)) + 1):
            if words[-k:-1] == fw[:k - 1] and fw[k - 1].startswith(words[-1]):
                best = k
        if best:
            words[-1] = fw[best - 1]          # upgrade a truncated boundary word
            words.extend(fw[best:])
        else:
            words.extend(fw)
    # 3. Collapse any immediately-repeated run of words ('you can you can' -> 'you
    #    can', 'should should' -> 'should'), which the typewriter leaves inside a
    #    single fragment. Longest block first, up to a short phrase.
    out: list[str] = []
    i, n = 0, len(words)
    while i < n:
        for span in range(min(4, (n - i) // 2), 0, -1):
            if words[i:i + span] == words[i + span:i + 2 * span]:
                out.extend(words[i:i + span])
                i += 2 * span
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)
