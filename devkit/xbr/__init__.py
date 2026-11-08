"""the XBR file tools: a TOC entry's records classified, two archives
diffed, a file edited, its pointer graph listed and checked

Modkit's ``azurik-mod xbr`` verbs, ported in Step 4.6l; each verb's
reference is ``devkit/xbr/README.md``."""

VERBS = {
    "inspect": "classify the first records of a TOC entry's payload, column by column",
    "diff": "what differs between two XBR files: tags' sizes, strings and in-place byte changes",
    "edit": "write an XBR file's strings, bytes and keyed cells into a new file",
    "xref": "list the pointer fields AzurKit's parse models, by owner tag, and the sections it doesn't",
    "verify": "check that an XBR file parses whole, and the packs' config.xbr cells against the schema",
}
