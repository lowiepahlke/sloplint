#!/usr/bin/env python3
"""sloplint.py - deterministic AI-slop linter for copy (English + Dutch).

Usage:
    python sloplint.py draft.txt [--format reply|answer|email|dm|post|x|landing|ad|long] [--lang auto|en|nl] [--json]
    echo "text" | python sloplint.py - --format email

Exit code: 0 = PASS, 1 = REVIEW, 2 = REWRITE.

What it checks (all deterministic, no model calls):
  1. Hard tells: contrast frames ("it's not X, it's Y"), throat-clearing openers, engagement bait,
     fake-profound closers, customer-service sign-offs, chatbot leakage, sycophancy, em dashes in short copy.
  2. Vocabulary: the 2024-2026 AI word list (EN + NL), puffery, weasel attribution, -ing tails, filler transitions.
  3. Rhythm: sentence-length burstiness, runs of same-length sentences, staccato fragments, one-word payoffs,
     paragraph uniformity, LinkedIn broetry, sentence-initial The/This/It.
  4. Specificity: share of sentences carrying a number, name, date, quote or first-person detail.
  5. Formatting: markdown in prose, bold-stem bullets, emoji, hashtags, title case, curly/straight mix, en dash ranges.
  6. Length per format.

Scoring: each finding has a severity 1-3. density = severity points per 100 words.
  PASS    density < 1.5 and no hard tell
  REVIEW  density 1.5-4.0, or one hard tell
  REWRITE density > 4.0, or 2+ hard tells, or 3+ severity-2+ findings inside 250 words

The verdict is a smoke alarm, not a judge. A PASS still needs a human read.
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------

EN_STOP = set("the and of to a in is that it you for on with this are be as at or not your but have we they from all can will just so if about what when one more no do".split())
NL_STOP = set("de het een en van dat niet je is op voor met zijn ook maar dit wat als bij om dan nog naar kan wel geen meer al dus hier veel echt gewoon jij jou jouw wij ons onze ik mijn".split())

# severity 2 unless noted. Regex fragments, matched case-insensitively with word boundaries.
EN_AI_WORDS = [
    r"delve\w*", r"tapestry", r"landscape", r"realm", r"pivotal", r"crucial", r"robust", r"seamless(?:ly)?",
    r"leverag(?:e|es|ed|ing)\s+(?:the|your|our|this|these|its|ai|data|technology|power)", r"unlock(?:s|ing)?\s+(?:the|your|new|a)",
    r"elevat(?:e|es|ed|ing)", r"supercharg\w*", r"empower\w*", r"foster(?:s|ed|ing)?", r"harness(?:es|ed|ing)?", r"streamlin\w*",
    r"game[- ]chang\w*", r"cutting[- ]edge", r"state[- ]of[- ]the[- ]art", r"transformative", r"paradigm", r"multifaceted",
    r"meticulous(?:ly)?", r"intricate", r"underscor(?:e|es|ed|ing)", r"showcas(?:e|es|ed|ing)", r"enduring", r"vibrant", r"bustling",
    r"beacon", r"ever[- ]evolving", r"fast[- ]paced", r"navigat(?:e|es|ing)\s+(?:the|this|these|your|today)", r"journey",
    r"embark\w*", r"unleash\w*", r"actionable", r"synergy", r"holistic", r"groundbreaking", r"revolutioni[sz]\w*",
    r"effortless(?:ly)?", r"utili[sz]\w*", r"facilitat\w*", r"myriad", r"plethora", r"nuanced", r"spearhead\w*", r"bolster\w*",
    r"curated", r"nestled", r"boasts?", r"commendable", r"noteworthy", r"invaluable", r"testament", r"resonat\w*",
    r"align(?:s|ed|ing)?\s+with", r"future[- ]proof\w*", r"\b10x\b", r"next[- ]level", r"world[- ]class", r"best[- ]in[- ]class",
    r"deep[- ]dive", r"dive\s+into", r"unpack(?:s|ed|ing)?\b", r"top[- ]notch", r"a\s+must[- ]have", r"look\s+no\s+further",
    r"whether\s+you'?re\s+a", r"imagine\s+(?:a\s+world|if|being)", r"in\s+today'?s", r"in\s+an\s+era", r"in\s+the\s+age\s+of",
    r"in\s+a\s+world\s+where", r"the\s+digital\s+age", r"digital\s+landscape", r"ecosystem", r"comprehensive", r"innovative",
]
EN_FILLER = [  # severity 1
    r"additionally", r"furthermore", r"moreover", r"notably", r"importantly", r"crucially", r"ultimately", r"in\s+conclusion",
    r"in\s+summary", r"overall,", r"in\s+other\s+words", r"that\s+being\s+said", r"needless\s+to\s+say", r"rest\s+assured",
    r"it\s+goes\s+without\s+saying", r"moving\s+forward", r"going\s+forward", r"in\s+order\s+to", r"when\s+it\s+comes\s+to",
    r"at\s+its\s+core", r"at\s+the\s+heart\s+of", r"in\s+the\s+realm\s+of", r"in\s+the\s+world\s+of", r"genuinely", r"quietly",
    r"truly", r"deeply", r"not\s+only", r"think\s+of\s+it\s+(?:like|as)", r"here'?s\s+(?:why|how)", r"to\s+provide\s+a\s+quick\s+update",
    r"after\s+careful\s+consideration", r"it'?s\s+(?:worth\s+noting|important\s+to\s+note)", r"key\s+takeaways?", r"insights?\b",
    r"ensure(?:s|d)?\b", r"significant(?:ly)?", r"efficient(?:ly)?", r"optimi[sz]\w*", r"solutions?\b",
]
EN_PUFFERY = [
    r"a\s+testament\s+to", r"marks\s+a\s+(?:pivotal|significant|new|major)", r"plays?\s+a\s+(?:vital|crucial|key|pivotal|significant)\s+role",
    r"stands\s+as", r"serves\s+as\s+a", r"solidif\w*", r"(?:underscores|highlights)\s+the\s+importance", r"cannot\s+be\s+overstated",
    r"pivotal\s+moment", r"commitment\s+to\s+(?:excellence|innovation|quality)", r"rich\s+(?:history|heritage)", r"enduring\s+legacy",
]
EN_WEASEL = [
    r"experts?\s+(?:agree|say|argue|believe)", r"studies\s+show", r"research\s+shows", r"many\s+(?:people|experts|argue)",
    r"industry\s+reports", r"it\s+is\s+widely", r"widely\s+regarded", r"some\s+(?:say|argue)", r"observers\s+note",
]
EN_ING_TAIL = r",\s+(?:highlighting|underscoring|showcasing|reflecting|emphasi[sz]ing|demonstrating|signal(?:l)?ing|marking|solidifying|cementing|reinforcing|illustrating|proving|ensuring|allowing|enabling|paving\s+the\s+way|setting\s+the\s+stage|making\s+it)\b"

EN_OPENERS = [  # throat-clearing / faux insight / engagement bait; severity 3 at text start, 2 elsewhere
    r"here'?s\s+the\s+(?:thing|kicker|catch|truth|part|deal|secret)", r"here'?s\s+what\s+(?:nobody|no\s+one|most\s+people)",
    r"here'?s\s+where\s+it\s+gets\s+interesting", r"let\s+me\s+be\s+clear", r"i'?ll\s+be\s+honest", r"the\s+(?:truth|reality|uncomfortable\s+truth)\s+is",
    r"real\s+talk", r"let'?s\s+(?:dive|unpack|break\s+(?:it|this)\s+down|talk\s+about|be\s+honest|face\s+it)", r"what\s+(?:most\s+people|nobody|no\s+one)\s+(?:miss|get\s+wrong|tell|realize|realise|understand)",
    r"most\s+people\s+don'?t\s+(?:realize|realise|know|understand)", r"the\s+part\s+(?:nobody|no\s+one|everyone)", r"think\s+about\s+it",
    r"plot\s+twist", r"spoiler(?:\s+alert)?:", r"the\s+interesting\s+part\s+is", r"(?:what\s+)?makes\s+this\s+(?:particularly\s+)?interesting",
    r"that'?s\s+the\s+(?:beauty|magic|power)\s+of", r"the\s+best\s+part\??", r"hot\s+take", r"unpopular\s+opinion", r"let\s+that\s+sink\s+in",
    r"read\s+that\s+again", r"full\s+stop\.", r"this\s+changes\s+everything", r"are\s+you\s+paying\s+attention", r"you'?re\s+not\s+ready\s+for",
    r"that'?s\s+it\.\s+that'?s\s+the", r"and\s+that\s+matters", r"that'?s\s+the\s+part\s+everyone\s+misses", r"which\s+is\s+exactly\s+the\s+point",
    r"what\s+if\s+i\s+told\s+you", r"stay\s+with\s+me", r"bear\s+with\s+me", r"the\s+implications\s+here", r"to\s+put\s+this\s+in\s+perspective",
    r"once\s+you\s+see\s+it", r"you\s+can'?t\s+unsee", r"the\s+bigger\s+picture", r"this\s+raises\s+the\s+question", r"with\s+that\s+being\s+said",
    r"great\s+question", r"thanks\s+for\s+sharing", r"you\s+raise\s+a", r"what\s+a\s+(?:thoughtful|great)", r"you'?re\s+absolutely\s+right",
    r"i\s+hope\s+this\s+(?:email|message)\s+finds\s+you", r"hope\s+you'?re\s+(?:doing\s+)?well", r"i\s+hope\s+all\s+is\s+well",
]
EN_CLOSERS = [  # severity 3 when in the last two sentences
    r"hope\s+this\s+helps", r"let\s+me\s+know\s+if\s+you\s+have\s+any\s+questions", r"feel\s+free\s+to", r"don'?t\s+hesitate",
    r"i'?d\s+be\s+happy\s+to", r"happy\s+to\s+(?:chat|discuss|help|walk\s+you\s+through|connect)", r"looking\s+forward\s+to\s+hearing",
    r"i\s+look\s+forward\s+to", r"(?:best|kind|warm)\s+regards", r"to\s+your\s+success", r"would\s+love\s+to\s+(?:chat|connect|hear)",
    r"let'?s\s+connect", r"the\s+future\s+(?:is|isn'?t|is\s+already)", r"it'?s\s+already\s+here", r"one\s+thing\s+is\s+clear",
    r"welcome\s+to\s+the\s+future", r"the\s+best\s+is\s+yet\s+to\s+come", r"because\s+in\s+the\s+end", r"at\s+the\s+end\s+of\s+the\s+day",
    r"the\s+journey\s+(?:doesn'?t\s+end|continues|is)", r"in\s+short,", r"the\s+choice\s+is\s+yours", r"only\s+time\s+will\s+tell",
    r"the\s+truth\s+lies\s+somewhere", r"stay\s+tuned", r"what'?s\s+your\s+(?:experience|take)\??", r"let\s+me\s+know\s+in\s+the\s+comments",
    r"agree\??$", r"thoughts\??$",
]
EN_EMAIL_OPENERS = [  # fake personalization, severity 2
    r"i\s+noticed\s+(?:your|that\s+you)", r"i\s+came\s+across\s+your", r"i\s+saw\s+your\s+(?:post|profile|recent)", r"i\s+was\s+impressed\s+by",
    r"i\s+love\s+what\s+you'?re\s+doing", r"i'?m\s+\w+\s+from\s+", r"my\s+name\s+is\s+\w+\s+and\s+i", r"i\s+(?:really\s+)?(?:like|admire)\s+your\s+(?:company'?s\s+)?mission",
    r"as\s+(?:a|the)\s+(?:founder|ceo|owner)\s+of", r"for\s+a\s+(?:founder|owner)-led", r"reaching\s+out\s+because", r"i\s+wanted\s+to\s+(?:reach\s+out|follow\s+up|touch\s+base)",
    r"i\s+hope\s+you\s+don'?t\s+mind",
]
EN_LEAK = [  # chatbot leakage, severity 3
    r"as\s+an\s+ai", r"here\s+is\s+a\s+(?:rewritten|revised|polished)", r"here'?s\s+a\s+(?:rewritten|revised|polished)\s+version", r"^\s*certainly[!,]",
    r"^\s*absolutely[!,]", r"^\s*sure[!,]\s+here", r"\[your\s+name\]", r"\[company\]", r"\[insert", r"i\s+hope\s+this\s+(?:helps|is\s+what)",
    r"let\s+me\s+know\s+if\s+you'?d\s+like\s+me\s+to", r"would\s+you\s+like\s+me\s+to",
]

NL_AI_WORDS = [
    r"cruciaal|cruciale", r"essentieel|essenti[eë]le", r"naadlo(?:os|ze)", r"landschap", r"transform(?:eren|eert|atie|atief|erende)",
    r"innovatie(?:f|ve)", r"wendbaar(?:heid)?", r"holistisch\w*", r"ecosysteem", r"waardepropositie", r"disruptie(?:f|ve)", r"ongekend\w*",
    r"derhalve", r"zodoende", r"aldus", r"betreffende", r"scala\s+aan", r"duik(?:en|t)?\s+(?:in|dieper|erin)", r"^\s*ontdek\b", r"ontdek\s+hoe",
    r"van\s+cruciaal\s+belang", r"lichtend\s+voorbeeld", r"baken\s+van", r"standvastig\w*", r"in\s+de\s+diepten", r"aangedreven",
    r"revolutionair\w*", r"boost(?:en|te)?\b", r"ontketen\w*", r"naar\s+een\s+hoger\s+niveau", r"benut(?:ten|t)?\b", r"faciliter\w*",
    r"waarborg\w*", r"stroomlijn\w*", r"game[- ]?changer", r"het\s+verschil\s+maken", r"trots\s+(?:om\s+te|te\s+mogen)\s+delen",
    r"in\s+het\s+huidige\s+landschap", r"in\s+de\s+snel\s+veranderende", r"in\s+het\s+digitale\s+tijdperk", r"in\s+dit\s+tijdperk",
    r"in\s+de\s+wereld\s+van\s+vandaag", r"het\s+is\s+belangrijk\s+om\s+op\s+te\s+merken", r"het\s+is\s+de\s+moeite\s+waard", r"dat\s+blijkt\s+uit",
    r"onmisbaar", r"inspirerend\w*", r"impactvol\w*", r"resoneer\w*|resoneert", r"authentiek\w*", r"toekomstbestendig\w*", r"state[- ]of[- ]the[- ]art",
    r"cutting[- ]edge", r"next[- ]level", r"ontgrendel\w*", r"verhoog\s+je", r"til\s+(?:je|jouw|uw)\s+\w+\s+naar", r"of\s+je\s+nu\s+\w+\s+bent\s+of",
    r"kijk\s+niet\s+verder", r"stel\s+je\s+voor\s+dat", r"het\s+resultaat\?", r"geen\s+zorgen", r"wees\s+gerust", r"krachtig\w*",
    r"optimaliseer\w*|optimaliseren", r"maximaliseer\w*|maximaliseren", r"waardevol\w*", r"uitgebreid\w*", r"veelzijdig\w*", r"dynamisch\w*",
    r"synergie", r"strategisch\w*", r"duurzame\s+(?:relaties|groei)", r"op\s+maat", r"zorgeloos", r"moeiteloos", r"ultieme", r"unieke\s+kans",
    r"leer\s+alles\s+over", r"lees\s+meer!", r"laat\s+je\s+inspireren", r"neem\s+de\s+controle", r"zet\s+de\s+volgende\s+stap",
]
NL_FILLER = [
    r"bovendien", r"verder\s+is", r"samenvattend", r"concluderend", r"al\s+met\s+al", r"uiteindelijk", r"in\s+essentie", r"in\s+de\s+kern",
    r"als\s+het\s+gaat\s+om", r"wanneer\s+het\s+aankomt\s+op", r"niet\s+alleen\s+.{2,60}\s+maar\s+ook", r"kan\s+(?:je|u|jou)\s+helpen",
    r"zou\s+kunnen", r"in\s+dit\s+artikel", r"in\s+deze\s+blog", r"belangrijk\s+om\s+te\s+weten", r"het\s+belang\s+van",
]
NL_PUFFERY = [
    r"is\s+een\s+bewijs\s+van", r"speelt\s+een\s+(?:cruciale|essenti[eë]le|belangrijke|sleutel)rol", r"markeert\s+een", r"onderstreept\s+het\s+belang",
    r"kan\s+niet\s+worden\s+overschat", r"staat\s+symbool\s+voor", r"benadrukt\s+het\s+belang", r"toewijding\s+aan",
]
NL_WEASEL = [
    r"experts\s+(?:stellen|zeggen|zijn\s+het\s+eens)", r"onderzoek\s+(?:wijst\s+uit|toont\s+aan|laat\s+zien)", r"steeds\s+meer\s+(?:mensen|organisaties|bedrijven|ondernemers)",
    r"veel\s+mensen\s+(?:denken|zeggen|vinden)", r"algemeen\s+bekend", r"men\s+zegt",
]
NL_ING_TAIL = r",\s+wat\s+(?:benadrukt|onderstreept|aantoont|laat\s+zien|bewijst|illustreert|de\s+weg\s+vrijmaakt|bijdraagt\s+aan)\b"
NL_OPENERS = [
    r"laat\s+dat\s+even\s+bezinken", r"lees\s+dat\s+nog\s+eens", r"dit\s+verandert\s+alles", r"even\s+eerlijk", r"laten\s+we\s+eerlijk\s+zijn",
    r"het\s+punt\s+is", r"de\s+waarheid\s+is", r"de\s+realiteit\s+is", r"wat\s+de\s+meeste\s+mensen\s+niet\s+(?:weten|zien|beseffen|doorhebben)",
    r"wat\s+niemand\s+(?:je\s+)?vertelt", r"hier\s+komt\s+(?:het|ie)", r"(?:en\s+)?hier\s+is\s+de\s+kicker", r"het\s+mooie\s+is", r"het\s+interessante\s+is",
    r"laten\s+we\s+(?:erin\s+|eens\s+)?duiken", r"laten\s+we\s+het\s+hebben\s+over", r"denk\s+daar\s+eens\s+over\s+na", r"goede\s+vraag",
    r"bedankt\s+voor\s+het\s+delen", r"ik\s+hoop\s+dat\s+deze\s+(?:e-?mail|mail|bericht)\s+(?:je|u)\s+goed", r"ik\s+hoop\s+dat\s+alles\s+goed",
    r"stel\s+je\s+eens\s+voor", r"wist\s+je\s+dat", r"eerlijk\s+is\s+eerlijk", r"laten\s+we\s+wel\s+wezen", r"het\s+is\s+tijd\s+om",
]
NL_CLOSERS = [
    r"ik\s+hoop\s+dat\s+dit\s+helpt", r"laat\s+het\s+(?:me|mij)\s+weten\s+als\s+je\s+vragen\s+hebt", r"aarzel\s+niet", r"neem\s+gerust\s+contact",
    r"ik\s+help\s+je\s+graag\s+verder", r"wil\s+je\s+hier\s+meer\s+over\s+weten", r"plan\s+(?:gerust\s+)?een\s+(?:gesprek|call|afspraak)",
    r"de\s+toekomst\s+is", r"[eé][eé]n\s+ding\s+is\s+zeker", r"en\s+dat\s+is\s+precies", r"want\s+uiteindelijk", r"welkom\s+in", r"de\s+reis\s+(?:begint|gaat)",
    r"de\s+keuze\s+is\s+aan\s+jou", r"tot\s+slot", r"kortom,", r"wat\s+vind\s+jij\??", r"laat\s+het\s+weten\s+in\s+de\s+reacties", r"eens\??$",
    r"ik\s+kijk\s+ernaar\s+uit", r"met\s+vriendelijke\s+groet", r"samen\s+(?:maken|bouwen)\s+we",
]
NL_EMAIL_OPENERS = [
    r"ik\s+zag\s+(?:dat\s+je|je\s+(?:post|profiel|bericht))", r"ik\s+kwam\s+(?:je|jouw|uw)\s+\w*\s*tegen", r"ik\s+was\s+onder\s+de\s+indruk",
    r"mijn\s+naam\s+is\s+\w+\s+en\s+ik", r"ik\s+ben\s+\w+\s+van\s+", r"wat\s+een\s+(?:mooi|prachtig)\s+(?:bedrijf|salon|website)", r"ik\s+wilde\s+even\s+(?:contact\s+opnemen|checken|polsen)",
    r"ik\s+bewonder", r"als\s+(?:eigenaar|oprichter)\s+van",
]
NL_LEAK = [
    r"als\s+(?:een\s+)?ai[- ]taalmodel", r"hier\s+is\s+een\s+(?:herschreven|aangepaste|verbeterde|geoptimaliseerde)\s+versie", r"^\s*zeker[!,]",
    r"^\s*natuurlijk[!,]\s+hier", r"\[naam\]", r"\[bedrijf(?:snaam)?\]", r"\[vul", r"laat\s+me\s+weten\s+als\s+je\s+wilt\s+dat\s+ik", r"wil\s+je\s+dat\s+ik",
]

EN_CONTRAST = [
    (r"\b(?:isn'?t|is\s+not|aren'?t|are\s+not|wasn'?t|was\s+not|not)\s+(?:just|only|merely|simply)\b[^!?]{0,80}?\b(?:but|it'?s|it\s+is|that'?s|this\s+is)\b", "not just X, but Y"),
    (r"\b(?:it|this|that|which|the\s+\w+)\s*(?:'s|\s+is|\s+isn'?t|\s+is\s+not|\s+wasn'?t)\s+not\s+(?:a\s+|an\s+|about\s+)?[^.!?;,:]{2,60}[.;,:]\s*(?:it'?s|it\s+is|this\s+is|that'?s|that\s+is|but)\b", "it's not X, it's Y"),
    (r"\b(?:it|this|that)\s+isn'?t\s+(?:a\s+|an\s+|about\s+)?[^.!?;,:]{2,60}[.;,:]\s*(?:it'?s|it\s+is|this\s+is|that'?s|that\s+is)\b", "this isn't X. It's Y"),
    (r"\bless\s+(?:a\s+|an\s+|about\s+)?[^,.]{2,30},\s*more\s+", "less X, more Y"),
    (r"\bforget\s+[^.!?]{2,40}[.!?]\s+this\s+is\b", "forget X. This is Y"),
    (r"\bmore\s+than\s+just\s+(?:a|an)\b", "more than just a X"),
    (r"\bwe\s+don'?t\s+(?:do|sell|build)\s+[^.,;]{2,40}[.,;]\s*we\s+", "we don't do X, we do Y"),
    (r"\bthis\s+is(?:n'?t)?\s+about\s+[^.,;]{2,40}[.,;]\s*(?:it'?s|this\s+is)\s+about\b", "this isn't about X, it's about Y"),
]
NL_CONTRAST = [
    (r"\b(?:het\s+gaat|gaat\s+het|draait)\s+niet\s+(?:alleen\s+)?om\b[^!?]{2,80}?\b(?:maar|het\s+gaat|het\s+draait)\b", "het gaat niet om X, maar om Y"),
    (r"\bniet\s+(?:alleen|slechts|enkel)\b[^!?]{2,80}?\bmaar\s+(?:ook|juist|vooral)\b", "niet alleen X, maar ook Y"),
    (r"\b(?:dat|dit|het)\s+is\s+geen\s+[^.!?;,:]{2,60}[.;,:]\s*(?:dat|dit|het)\s+is\b", "dat is geen X. Dat is Y"),
    (r"\bgeen\s+[^.,;]{2,40},\s*maar\s+(?:een|het|de|wel)\b", "geen X, maar Y"),
    (r"\bminder\s+[^,.]{2,30},\s*meer\s+", "minder X, meer Y"),
    (r"\bmeer\s+dan\s+(?:alleen|zomaar)\s+(?:een|het|de)\b", "meer dan alleen een X"),
]

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F1E6-\U0001F1FF]")
TIME_WORDS = r"\b(?:yesterday|today|tomorrow|last\s+(?:week|month|year|night|tuesday|friday)|this\s+(?:morning|week|month)|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|june|july|august|september|october|november|december|gisteren|vandaag|morgen|vorige\s+(?:week|maand|jaar)|afgelopen\s+(?:week|maand|jaar)|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|januari|februari|maart|mei|juni|juli|augustus|oktober|november)\b"
FIRST_PERSON = r"\b(?:I|I'?m|I'?ve|I'?d|I'?ll|we|we'?re|we'?ve|my|our|me|ik|wij|we|mijn|ons|onze|mij|m'n)\b"

FORMAT_LIMITS = {  # (soft, hard) word limits
    "reply": (40, 70), "answer": (120, 180), "email": (125, 180), "dm": (80, 130), "post": (300, 450),
    "x": (60, 100), "landing": (45, 80), "ad": (70, 120), "long": (None, None),
}
SHORT_FORMATS = {"reply", "answer", "email", "dm", "x", "landing", "ad"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def detect_lang(text):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return "en"
    nl = sum(w in NL_STOP for w in words)
    en = sum(w in EN_STOP for w in words)
    return "nl" if nl > en else "en"


ABBR = ["e.g", "i.e", "vs", "mr", "mrs", "dr", "st", "etc", "bv", "bijv", "o.a", "p.s", "ca", "approx", "no", "nr", "jr", "sr", "min", "max", "incl", "excl", "resp"]


def split_sentences(par):
    t = par
    for a in ABBR:
        t = re.sub(r"\b" + re.escape(a) + r"\.", a.replace(".", "<dot>") + "<dot>", t, flags=re.I)
    t = re.sub(r"(\d)\.(\d)", r"\1<dot>\2", t)
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“(A-Z0-9€$@#*\-]|[a-z])", t)
    out = []
    for p in parts:
        p = p.replace("<dot>", ".").strip()
        if p:
            out.append(p)
    return out


def strip_markup(text):
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    return t


def wc(s):
    return len(re.findall(r"\S+", s))


class Findings:
    def __init__(self):
        self.items = []

    def add(self, category, code, severity, message, quote="", line=None):
        self.items.append({"category": category, "code": code, "severity": severity, "message": message,
                           "quote": quote.strip()[:140], "line": line})


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def scan_list(text, patterns, category, code, severity, F, message, limit=None, region=None):
    """Regex list scan. region=(start,end) restricts matches to a slice of text."""
    n = 0
    seen = set()
    for pat in patterns:
        for m in re.finditer(r"(?<![\w-])(?:" + pat + r")(?![\w-])" if not pat.startswith("^") else pat, text, flags=re.I | re.M):
            if region and not (region[0] <= m.start() < region[1]):
                continue
            key = m.group(0).lower()
            if key in seen and category in ("vocab", "filler"):
                continue
            seen.add(key)
            F.add(category, code, severity, message, m.group(0), line_of(text, m.start()))
            n += 1
            if limit and n >= limit:
                return n
    return n


# ---------------------------------------------------------------------------
# main lint
# ---------------------------------------------------------------------------

def lint(text, fmt="answer", lang="auto"):
    raw = text.replace("\r\n", "\n").strip()
    if lang == "auto":
        lang = detect_lang(raw)
    F = Findings()
    plain = strip_markup(raw)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\S)", plain) if p.strip()]
    sents, sent_par = [], []
    for i, p in enumerate(paragraphs):
        for s in split_sentences(p):
            sents.append(s)
            sent_par.append(i)
    words_total = wc(plain)
    lens = [wc(s) for s in sents]
    n_sent = len(sents)
    last_region = (max(0, len(raw) - max(200, len(raw) // 4)), len(raw) + 1)
    first_region = (0, min(len(raw), 220))

    # ---- 1. hard tells -----------------------------------------------------
    contrast = EN_CONTRAST if lang == "en" else NL_CONTRAST
    taken = []  # one phrase can match several contrast patterns; count it once
    for pat, name in contrast:
        for m in re.finditer(pat, raw, flags=re.I):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append(m.span())
            F.add("hard", "contrast-frame", 3, f"contrast frame ({name}): say the second half only", m.group(0), line_of(raw, m.start()))
    # negative listing: 2+ consecutive sentences starting with Not / Geen / No
    neg = re.compile(r"^(?:not|no|geen|niet)\s", re.I)
    run = 0
    for i, s in enumerate(sents):
        if neg.match(s) and lens[i] <= 8:
            run += 1
            if run == 2:
                F.add("hard", "negative-listing", 3, "negative listing (Not X. Not Y. Z.): just say Z", sents[i - 1] + " " + s)
        else:
            run = 0

    openers = EN_OPENERS if lang == "en" else NL_OPENERS
    scan_list(raw, openers, "hard", "throat-clearing", 3, F, "throat-clearing / faux insight / engagement bait: delete it and start one sentence later", region=first_region)
    scan_list(raw, openers, "hard", "engagement-bait", 2, F, "setup line that performs insight instead of giving it: delete", region=(first_region[1], len(raw) + 1))
    closers = EN_CLOSERS if lang == "en" else NL_CLOSERS
    scan_list(raw, closers, "hard", "canned-closer", 3, F, "customer-service sign-off or fake-profound closer: end on the last concrete point instead", region=last_region)
    scan_list(raw, closers, "hard", "canned-line", 2, F, "canned line: cut", region=(0, last_region[0]))
    leak = EN_LEAK if lang == "en" else NL_LEAK
    scan_list(raw, leak, "hard", "chatbot-leak", 3, F, "chatbot leakage: this text was pasted from a model, remove the wrapper")
    if fmt in ("email", "dm"):
        eo = EN_EMAIL_OPENERS if lang == "en" else NL_EMAIL_OPENERS
        scan_list(raw, eo, "hard", "fake-personalization", 2, F, "reflected personalization opener readers now filter out: name their problem in one plain sentence instead")

    # em dashes
    emd = [m.start() for m in re.finditer("—", raw)]
    end = [m.start() for m in re.finditer(r"\s–\s|\s--\s", raw)]
    if emd or end:
        n = len(emd) + len(end)
        if fmt in SHORT_FORMATS:
            F.add("hard", "em-dash", 3, f"{n} dash(es) in short copy: use a period, comma or parentheses", raw[max(0, (emd + end)[0] - 40):(emd + end)[0] + 40])
        elif n > 2:
            F.add("hard", "em-dash", 2, f"{n} em/en dashes: keep at most 1-2 in long copy, and only where a comma or period fails", "")
        else:
            F.add("soft", "em-dash", 1, f"{n} em/en dash(es): fine in long copy if deliberate", "")
    for m in re.finditer(r"\d\s–\s\d", raw):
        F.add("soft", "en-dash-range", 1, "spaced en dash in a range (Monday – Friday): humans type a hyphen", m.group(0), line_of(raw, m.start()))

    # ---- 2. vocabulary -------------------------------------------------------
    vocab = EN_AI_WORDS if lang == "en" else NL_AI_WORDS
    filler = EN_FILLER if lang == "en" else NL_FILLER
    puff = EN_PUFFERY if lang == "en" else NL_PUFFERY
    weasel = EN_WEASEL if lang == "en" else NL_WEASEL
    scan_list(plain, vocab, "vocab", "ai-word", 2, F, "AI vocabulary: replace with the plain word or the specific fact")
    scan_list(plain, filler, "filler", "filler", 1, F, "filler / transition / hedge that delays the point")
    scan_list(plain, puff, "vocab", "puffery", 2, F, "importance puffery: state the fact and let the reader judge")
    scan_list(plain, weasel, "vocab", "weasel", 2, F, "weasel attribution: name the source or cut the claim")
    for m in re.finditer(EN_ING_TAIL if lang == "en" else NL_ING_TAIL, plain, flags=re.I):
        F.add("vocab", "ing-tail", 2, "participial tail that pretends to explain: cut it or say the consequence", plain[max(0, m.start() - 40):m.end() + 40], line_of(plain, m.start()))

    # ---- 3. structure & rhythm ------------------------------------------------
    # colon reveal
    for m in re.finditer(r"(?:(?<=^)|(?<=[.!?]\s)|(?<=\n))(?:The|My|Our|Its|His|Her|Their|Het|De|Mijn|Onze)\s[^:.!?\n]{2,45}:\s+([a-z][^.!?\n]{1,60})[.!?]", plain, flags=re.M):
        after = wc(m.group(1))
        if after <= 8:
            F.add("structure", "colon-reveal", 2 if after <= 4 else 1, "colon reveal (The best part: it learns.): write a plain sentence", m.group(0), line_of(plain, m.start()))
    # tricolon: three parallel short items
    tri = 0
    for m in re.finditer(r"\b([A-Za-z-]{3,12}),\s+([A-Za-z-]{3,12}),?\s+(?:and|en|&)\s+([A-Za-z-]{3,12})\b|\b([A-Za-z-]{3,12}),\s+([A-Za-z-]{3,12}),\s+([A-Za-z-]{3,12})[.!]", plain):
        w = [x.lower() for x in m.groups() if x]
        if any(x in EN_STOP or x in NL_STOP for x in w):
            continue
        tri += 1
        F.add("structure", "rule-of-three", 1 if tri == 1 else 2, "rule of three: real life gives two reasons, or five; keep the one that is true", m.group(0), line_of(plain, m.start()))
    # staccato runs and pairs
    run = 0
    for i, L in enumerate(lens):
        if L <= 4 and (i == 0 or sent_par[i] == sent_par[i - 1]):
            run += 1
            if run == 3:
                F.add("structure", "staccato", 2, "three consecutive fragments (Fast. Simple. Done.): merge into one sentence", " ".join(sents[i - 2:i + 1]))
        else:
            run = 1 if L <= 4 else 0
    for i in range(1, n_sent):
        if lens[i] <= 3 and lens[i - 1] <= 3 and sent_par[i] == sent_par[i - 1] and not sents[i - 1].endswith("?"):
            F.add("structure", "staccato-pair", 2, "staccato pair (No fluff. Just answers.): pick one", sents[i - 1] + " " + sents[i])
            break
    for i in range(1, n_sent):
        if sents[i - 1].endswith("?") and lens[i] <= 3 and sent_par[i] == sent_par[i - 1]:
            F.add("structure", "question-payoff", 2, "rhetorical question with a one-word payoff (The result? Chaos.): state it plainly", sents[i - 1] + " " + sents[i])
    nq = sum(s.endswith("?") for s in sents)
    if nq >= 2 and words_total < 250 and fmt != "reply":
        F.add("structure", "rhetorical-questions", 1, f"{nq} questions in {words_total} words: questions you answer yourself read as padding", "")

    # rhythm statistics
    stats = {"words": words_total, "sentences": n_sent, "paragraphs": len(paragraphs), "lang": lang, "format": fmt}
    if n_sent >= 3:
        mean = statistics.mean(lens)
        sd = statistics.pstdev(lens) if n_sent > 1 else 0
        burst = round(sd / mean, 2) if mean else 0
        stats.update({"mean_sentence_len": round(mean, 1), "sd_sentence_len": round(sd, 1), "burstiness": burst,
                      "shortest": min(lens), "longest": max(lens)})
        if n_sent >= 6 and burst < 0.35:
            F.add("rhythm", "low-burstiness", 2, f"sentence lengths barely vary (burstiness {burst}, aim for 0.5+): one long sentence, then a short one", "")
        run, best = 0, 0
        for L in lens:
            run = run + 1 if 15 <= L <= 25 else 0
            best = max(best, run)
        if best >= 3:
            F.add("rhythm", "even-run", 2 if best >= 4 else 1, f"{best} consecutive sentences of 15-25 words: metronome cadence", "")
        starters = r"^(?:the|this|it|in|there)\b" if lang == "en" else r"^(?:de|het|dit|er|in|dat)\b"
        ns = sum(bool(re.match(starters, s, flags=re.I)) for s in sents)
        stats["starter_share"] = round(ns / n_sent, 2)
        if n_sent >= 6 and ns / n_sent > 0.5:
            first = "The/This/It/In" if lang == "en" else "De/Het/Dit/Er"
            F.add("rhythm", "same-starters", 1, f"{ns}/{n_sent} sentences start with {first}: vary the first word", "")
    if len(paragraphs) >= 4:
        pl = [wc(p) for p in paragraphs]
        pm = statistics.mean(pl)
        pu = round(statistics.pstdev(pl) / pm, 2) if pm else 0
        stats["paragraph_uniformity"] = pu
        if pu < 0.25 and pm > 12:
            F.add("rhythm", "uniform-paragraphs", 1, "every paragraph is the same size: let one run long and one be a single line", "")
        single = sum(len(split_sentences(p)) == 1 for p in paragraphs)
        if len(paragraphs) >= 6 and single / len(paragraphs) >= 0.8 and fmt not in ("x",):
            F.add("rhythm", "broetry", 2 if fmt != "post" else 1, f"{single}/{len(paragraphs)} paragraphs are one line: LinkedIn broetry now reads as AI; group related lines", "")

    # ---- 4. specificity -------------------------------------------------------
    anchored, considered = 0, 0
    for i, s in enumerate(sents):
        if lens[i] < 8:
            continue
        considered += 1
        body = s[1:] if s else s
        proper = re.search(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]{2,}", body) and not re.fullmatch(r"[A-Z][a-z]+", body.strip())
        ok = (re.search(r"\d", s) or re.search(r"[€$£%]", s) or proper or re.search(r"[\"“”]", s)
              or re.search(FIRST_PERSON, s) or re.search(TIME_WORDS, s, flags=re.I) or "@" in s)
        anchored += bool(ok)
    if considered >= 3:
        share = round(anchored / considered, 2)
        stats["anchored_share"] = share
        if share < 0.4:
            F.add("specific", "generic", 2, f"only {anchored}/{considered} longer sentences carry a number, name, quote, date or first-person detail: the copy is portable, add the thing only you could write", "")
    for m in re.finditer(r"\b\d+\s*(?:to|-|–|tot)\s*\d+\s*(?:minutes|mins|hours|hrs|days|weeks|months|minuten|uur|dagen|weken|maanden)\b", plain, flags=re.I):
        F.add("specific", "fake-range", 1, "a range (5 to 10 minutes) reads as never done: give the one number you measured", m.group(0), line_of(plain, m.start()))
    if lang == "en" and n_sent >= 8 and not re.search(r"\b\w+(?:'s|'re|'ve|'ll|'d|n't|'m)\b", plain):
        F.add("specific", "no-contractions", 1, f"zero contractions in {n_sent} sentences: people say it's and don't", "")

    # ---- 5. formatting ----------------------------------------------------------
    if re.search(r"^\s{0,3}#{1,6}\s+", raw, flags=re.M) and fmt in SHORT_FORMATS | {"post"}:
        F.add("format", "markdown-header", 2, "markdown headers in copy nobody formats: sentences instead", "")
    bold = re.findall(r"\*\*[^*]+\*\*", raw)
    if bold:
        F.add("format", "bold", 2 if len(bold) > 1 or fmt in SHORT_FORMATS else 1, f"{len(bold)} bold span(s): decoration, not emphasis", bold[0])
    if re.search(r"^\s*[-*•]\s+\*\*[^*]+\*\*:?", raw, flags=re.M):
        F.add("format", "bold-stem-bullets", 3, "bullets with bold stems and colons: the ChatGPT list; write prose", "")
    if fmt in SHORT_FORMATS and re.search(r"^\s*(?:[-*•]|\d+[.)])\s+", raw, flags=re.M):
        F.add("format", "list-in-reply", 2, "a list inside a reply/email/ad: nobody bullets a message", "")
    em = EMOJI_RE.findall(raw)
    if len(em) > 1 and fmt in SHORT_FORMATS:
        F.add("format", "emoji", 2, f"{len(em)} emoji in short copy: one at most, and only as a shrug", "".join(em[:5]))
    elif len(em) > 3:
        F.add("format", "emoji", 2, f"{len(em)} emoji: decoration", "".join(em[:5]))
    if re.search(r"^\s*" + EMOJI_RE.pattern, raw, flags=re.M):
        F.add("format", "emoji-bullets", 3, "emoji as bullets or headers (🚀 ✅ 💡): the marketing-blog training data talking", "")
    tags = re.findall(r"(?<!\w)#\w{3,}", raw)
    if tags:
        F.add("format", "hashtags", 2 if fmt != "x" else 1, f"{len(tags)} hashtag(s): cut", " ".join(tags[:4]))
    for m in re.finditer(r"^(?:[A-Z][a-z]+(?:\s+(?:of|the|and|in|to|a|for|with|on))*\s+){2,7}[A-Z][a-z]+:?\s*$", raw, flags=re.M):
        F.add("format", "title-case", 1, "Title Case Heading: humans write headings like sentences", m.group(0), line_of(raw, m.start()))
    if "’" in raw and re.search(r"\w'\w", raw):
        F.add("format", "mixed-quotes", 1, "curly and straight apostrophes mixed: pasted from a model or a doc", "")
    if fmt in SHORT_FORMATS and ";" in plain:
        F.add("format", "semicolon", 1, "semicolon in short copy: nobody types those in a message", "")
    excl = plain.count("!")
    if words_total and excl / max(words_total, 1) > 0.03 and excl >= 3:
        F.add("format", "performed-enthusiasm", 1, f"{excl} exclamation marks in {words_total} words: performed enthusiasm", "")

    # ---- 6. length -----------------------------------------------------------------
    soft, hard = FORMAT_LIMITS.get(fmt, (None, None))
    if hard and words_total > hard:
        F.add("length", "too-long", 3 if words_total > hard * 1.4 else 2, f"{words_total} words for a {fmt} (hard limit {hard}): the easiest AI tell is length; halve it", "")
    elif soft and words_total > soft:
        F.add("length", "long", 1, f"{words_total} words for a {fmt} (aim under {soft})", "")

    # ---- scoring -------------------------------------------------------------------
    points = sum(f["severity"] for f in F.items)
    hard_tells = [f for f in F.items if f["severity"] == 3]
    strong = [f for f in F.items if f["severity"] >= 2]
    density = round(points / max(words_total, 50) * 100, 2)
    if density > 4.0 or len(hard_tells) >= 2 or (len(strong) >= 3 and words_total <= 250):
        verdict = "REWRITE"
    elif density >= 1.5 or len(hard_tells) == 1:
        verdict = "REVIEW"
    else:
        verdict = "PASS"
    order = {"hard": 0, "length": 1, "structure": 2, "vocab": 3, "rhythm": 4, "specific": 5, "format": 6, "filler": 7, "soft": 8}
    F.items.sort(key=lambda f: (-f["severity"], order.get(f["category"], 9), f["line"] or 0))
    cats = Counter(f["category"] for f in F.items)
    return {"verdict": verdict, "density": density, "points": points, "hard_tells": len(hard_tells), "stats": stats,
            "categories": dict(cats), "findings": F.items}


def render(res):
    s = res["stats"]
    out = [f"sloplint: {s['words']} words, {s['sentences']} sentences, {s['paragraphs']} paragraphs, lang={s['lang']}, format={s['format']}",
           f"VERDICT: {res['verdict']}  (density {res['density']} pts/100w, {res['hard_tells']} hard tell(s), {len(res['findings'])} finding(s))"]
    if "burstiness" in s:
        out.append(f"rhythm: mean {s['mean_sentence_len']}w, sd {s['sd_sentence_len']}, burstiness {s['burstiness']} (aim 0.5+), shortest {s['shortest']}w, longest {s['longest']}w"
                   + (f", {int(s['starter_share']*100)}% start with " + ("The/This/It" if s["lang"] == "en" else "De/Het/Dit")
                      if "starter_share" in s else ""))
    if "anchored_share" in s:
        out.append(f"specificity: {int(s['anchored_share']*100)}% of longer sentences carry a number, name, quote, date or first-person detail (aim 40%+)")
    if not res["findings"]:
        out.append("no findings. Now do the human read: would the person named as author type this?")
        return "\n".join(out)
    out.append("")
    for f in res["findings"]:
        loc = f"L{f['line']}" if f["line"] else "   "
        q = f"  \"{f['quote']}\"" if f["quote"] else ""
        out.append(f"[{f['severity']}] {loc:>4} {f['code']:<20} {f['message']}{q}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="AI-slop linter for copy (EN/NL)")
    ap.add_argument("path", help="file to lint, or - for stdin")
    ap.add_argument("--format", default="answer", choices=sorted(FORMAT_LIMITS))
    ap.add_argument("--lang", default="auto", choices=["auto", "en", "nl"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    # Windows consoles default to a legacy codepage; read and print UTF-8 everywhere.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    text = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8-sig").read()
    res = lint(text, a.format, a.lang)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else render(res))
    sys.exit({"PASS": 0, "REVIEW": 1, "REWRITE": 2}[res["verdict"]])


if __name__ == "__main__":
    main()
