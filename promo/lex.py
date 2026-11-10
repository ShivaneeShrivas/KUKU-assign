"""Genre lexicons. Deliberately generic microdrama vocabulary (period AND modern),
not tuned to one show, so the tool still works on a new series."""
import re

def rx(words):
    return re.compile(r"\b(?:" + "|".join(words) + r")", re.I)

# --- hook / stop-power categories: (weight, regex) -------------------------------
STOP = {
    "physical": (1.00, rx([r"slap\w*", r"strik\w+", r"struck", r"shov\w+", r"hurl\w*", r"thr(?:ow|ew|own)\w*", r"grab\w*",
                           r"drag\w*", r"seiz\w+", r"whip\w*", r"blood\w*", r"bleed\w*", r"knife", r"dagger", r"sword",
                           r"blade", r"gun", r"pistol", r"wound\w*", r"stab\w*", r"chok\w+", r"punch\w*", r"kick\w*",
                           r"slam\w*", r"shatter\w*", r"smash\w*", r"collaps\w+", r"tear[s]? (?:the|her|his)", r"crack of",
                           r"splash\w*", r"drench\w*", r"pour\w* (?:wine|water|tea)", r"force\w* (?:her|him) to"])),
    "stakes": (0.90, rx([r"die\b", r"dead", r"death", r"dying", r"kill\w*", r"murder\w*", r"poison\w*", r"arsenic", r"execut\w+",
                         r"hang(?:ed|ing)?\b", r"gallows", r"hostage", r"prison\w*", r"dungeon", r"arrest\w*", r"gun\w*",
                         r"ransom", r"sentenc\w+", r"condemn\w*", r"burn(?:ed|ing)?\b", r"drown\w*", r"missing", r"kidnap\w*"])),
    "reveal": (0.85, rx([r"reveal\w*", r"secret\w*", r"the truth", r"truth", r"alive", r"who are you", r"what are you",
                         r"you(?:'re| are) not", r"i am the", r"i'm the", r"pregnan\w+", r"\bbaby\b", r"paternity", r"\bdna\b",
                         r"divorc\w+", r"annul\w*", r"betray\w*", r"traitor\w*", r"\bliars?\b", r"\blied\b", r"\blies\b",
                         r"impost\w+", r"fake", r"identity", r"all along", r"you knew", r"i knew", r"heir\b", r"true (?:name|identity|self)",
                         r"duke\b", r"\bking\b", r"queen\b", r"prince\w*", r"billionaire", r"\bceo\b", r"affair", r"cheat\w*", r"mistress"])),
    "confront": (0.65, rx([r"how dare", r"get out", r"leave (?:now|this|my)", r"kneel\w*", r"\bbeg\b", r"begging", r"shut (?:up|your)",
                           r"silence", r"enough", r"you will (?:pay|regret|obey)", r"or else", r"i will (?:not|never|make|see|have)",
                           r"don'?t you (?:dare|touch)", r"how could you", r"explain yourself", r"answer me", r"look at me",
                           r"you(?:'ve| have) (?:gone|crossed)", r"guards?\b", r"seize (?:her|him)", r"take (?:her|him) away",
                           r"\bstop\b", r"let (?:her|him) go", r"release (?:her|him)", r"step away", r"i object", r"that is a lie"])),
    "status": (0.70, rx([r"disown\w*", r"beggar", r"worthless", r"plain(?:ness)?", r"shame\w*", r"disgrace\w*", r"humiliat\w+",
                         r"pathetic", r"nothing (?:but|more)", r"inherit\w*", r"stripped", r"banish\w*", r"exile\w*", r"cast (?:out|aside)",
                         r"unworthy", r"low value", r"commoner", r"servant", r"fired", r"expel\w*", r"in front of (?:everyone|them all|all)",
                         r"before (?:everyone|the whole|all)", r"laugh\w* at", r"mock\w*", r"jeer\w*", r"whisper\w* (?:and|among)"])),
    "romance": (0.50, rx([r"marry me", r"be my wife", r"be my husband", r"my wife", r"my husband", r"\bkiss\w*", r"\bmine\b",
                          r"embrace\w*", r"lips", r"i love you", r"don'?t (?:go|leave)", r"stay with me", r"wedding", r"vow\w*",
                          r"bride", r"groom", r"proposal", r"propos\w+", r"fiance\w*", r"engage\w+"])),
}

# --- intensity tone tags (appear in parentheses after speaker) -------------------
TONE_HI = rx([r"shout\w*", r"scream\w*", r"furious", r"enrag\w+", r"outrag\w+", r"desperat\w+", r"panick\w*", r"gasp\w*",
              r"stunn\w+", r"shock\w*", r"horrif\w+", r"menac\w+", r"venom\w+", r"icy", r"trembl\w+", r"sob\w*", r"anguish\w*",
              r"thunder\w*", r"roar\w*", r"snarl\w*", r"command\w*", r"accus\w+", r"defiant", r"cold", r"seeth\w+", r"cruel",
              r"savage", r"vicious", r"hiss\w*", r"explosive", r"breathless", r"terrif\w+", r"agoni\w+", r"piercing", r"scath\w+",
              r"unyielding", r"lethal", r"deadly", r"fierce", r"raging", r"incredulous", r"betrayed", r"devastat\w+", r"shatter\w*"])
TONE_LO = rx([r"sorrow\w*", r"\bsad\b", r"mourn\w*", r"wistful", r"loving", r"earnest", r"reassuring", r"soft\w*", r"gentl\w+", r"warm", r"tender", r"calm", r"relieved", r"grateful", r"peaceful", r"quiet\w*",
              r"affectionate", r"cheerful", r"amused", r"light\w*", r"playful", r"content"])

# --- cliffhanger lexicons -------------------------------------------------------
CLIFF_REVEAL = rx([r"door", r"steps? (?:in|out|forward|into)", r"appear\w*", r"enter\w*", r"figure", r"silhouette", r"doorway",
                   r"unveil\w*", r"reveal\w*", r"pulls? (?:out|a|the|off)", r"draws?\b", r"aim\w*", r"point\w* (?:at|a|the)", r"discover\w*",
                   r"notices?", r"freez\w+", r"eyes? widen\w*", r"gasp\w*", r"drops?\b", r"shatter\w*", r"collaps\w+", r"unseen",
                   r"watching", r"lurk\w*", r"hidden", r"overhear\w*", r"witness\w*", r"walks? in", r"burst\w*", r"kick\w* open",
                   r"ring\b", r"letter", r"note\b", r"locket", r"poker", r"cell", r"dread", r"horror", r"paraly\w+", r"stunn\w+",
                   r"blood", r"scar", r"smirk\w*", r"cold smile", r"unreadable"])
CLIFF_THREAT = rx([r"will pay", r"regret", r"you(?:'re| are) (?:finished|done|dead)", r"no escape", r"last chance", r"by (?:dawn|morning|midnight|nightfall)",
                   r"tomorrow", r"tonight", r"before (?:dawn|sunrise|sunset)", r"i will (?:destroy|ruin|kill|end|find|make you)",
                   r"you(?:'ll| will) (?:never|not)", r"or (?:else|i)", r"\bunless\b", r"ultimatum", r"deadline", r"sentenc\w+",
                   r"die\b", r"kill", r"poison", r"arsenic", r"execut\w+", r"hang", r"it(?:'s| is) (?:you|him|her)", r"who (?:sent|told|did)",
                   r"what (?:did|have) you", r"you did this", r"know(?:s)? (?:everything|what you)"])
CLIFF_SOUND = rx([r"sting\w*", r"stinger", r"ominous", r"crescendo", r"swell\w*", r"boom", r"cliffhanger", r"drone", r"chord", r"silence",
                  r"abrupt", r"cut to black", r"cuts? to black", r"hold\w*"])
RESOLVE = rx([r"thank you", r"thanks", r"forgive\w*", r"i promise", r"of course", r"together", r"love you", r"\bsmiles?\b", r"laugh\w*",
              r"relief", r"relieved", r"it(?:'s| is) over", r"finally", r"\bsafe\b", r"peace\w*", r"\brest\b", r"\bnods?\b", r"\bbows?\b",
              r"agreed", r"accept\w*", r"\bwelcome\b", r"goodnight", r"good night", r"sleep\w*", r"fell asleep", r"warm\w*", r"tender\w*",
              r"home\b", r"fade\w* out", r"gentle", r"gently", r"serene", r"contentment"])

# --- context-debt lexicons ---------------------------------------------------------
BACKREF = rx([r"earlier", r"last night", r"yesterday", r"as i (?:said|told)", r"i told you", r"remember", r"you promised", r"the other day",
              r"as (?:we|you) discussed", r"as before", r"that (?:night|day)\b", r"back then", r"like (?:last|before)",
              r"you(?:'ve| have) (?:done|taken|made) (?:this|it) before", r"used to", r"ever since", r"what (?:you|they|he|she) did (?:to|that)"])
CONTINUATION = re.compile(r"^\s*[\"“]?\s*(?:\.{2,}|…|—|-{2,})", re.I)   # line that resumes a sentence: '...and killing my wife'
PRONOUN3 = re.compile(r"\b(?:he|she|him|her|his|hers|they|them|their)\b", re.I)
ANAPHORIC_OPEN = re.compile(r"^\s*[\"“]?(?:\.{2,}|…)?\s*(?:he|she|they|it|that|this|those|these|him|her|them|so|but|and|then|because|yes|no|please|well|also|still|however|either|neither|both)\b", re.I)
GREETING = re.compile(r"^\s*(?:good (?:morning|evening|day)|hello|hi\b|welcome|greetings|thank you|thanks|my lady|my lord|your grace)\b", re.I)
EXPOSITION = rx([r"let me explain", r"as you know", r"meanwhile", r"the story", r"it (?:all )?began", r"years ago", r"long ago", r"once upon"])
ROLE_WORDS = rx([r"wife", r"husband", r"fianc\w+", r"sister", r"brother", r"mother", r"father", r"mom\b", r"dad\b", r"daughter", r"son\b",
                 r"duke", r"duchess", r"lord", r"lady", r"king", r"queen", r"prince\w*", r"soldier", r"captain", r"general", r"master",
                 r"servant", r"maid", r"priest", r"judge", r"doctor", r"boss", r"\bceo\b", r"ex-?\w+", r"stepmother", r"stepsister", r"bride", r"groom",
                 r"guard", r"stranger", r"husband", r"widow", r"heir", r"mistress", r"nurse", r"officer"])
PREMISE = rx([r"my wife", r"my husband", r"married", r"wedding", r"marry", r"duke", r"soldier", r"disown\w*", r"inherit\w*",
              r"betray\w*", r"fianc\w+", r"poison\w*", r"divorc\w+", r"pregnan\w+"])

# --- trope / "emotional engine" tags used for portfolio diversity ----------------
ENGINES = {
    "Public humiliation": rx([r"humiliat\w+", r"shame\w*", r"disgrace\w*", r"disown\w*", r"guests", r"crowd", r"before (?:everyone|all)", r"in front of",
                              r"mock\w*", r"laugh\w* at", r"plain(?:ness)?", r"worthless", r"beggar", r"mud", r"stripped", r"banish\w*", r"whisper\w*"]),
    "Hidden identity / reveal": rx([r"duke\b", r"secret\w*", r"the truth", r"reveal\w*", r"identity", r"who are you", r"scar\w*", r"soldier", r"impost\w+",
                                    r"heir", r"true (?:name|self)", r"all along", r"alive", r"disguise\w*", r"mask\w*"]),
    "Protector / rescue": rx([r"protect\w*", r"rescu\w+", r"defend\w*", r"guards?\b", r"sword", r"blade", r"step(?:s|ped)? (?:in|between|forward)",
                              r"behind me", r"touch (?:her|him)", r"lethal", r"intervene\w*", r"shield\w*", r"save\w*", r"kneel\w*"]),
    "Poison / conspiracy": rx([r"poison\w*", r"arsenic", r"antidote", r"plot\w*", r"conspir\w+", r"witch\w*", r"gallows", r"treason\w*", r"scheme\w*",
                               r"evidence", r"trial", r"accus\w+", r"spy", r"informant", r"alliance", r"extort\w*", r"council", r"hang\w*", r"fabricat\w+"]),
    "Marriage / romance tension": rx([r"marry", r"married", r"wife", r"husband", r"wedding", r"vow\w*", r"kiss\w*", r"embrace\w*", r"bride", r"groom",
                                      r"proposal", r"propos\w+", r"love\b", r"heart", r"tend\w*", r"bandage\w*", r"intimate", r"lips", r"cottage"]),
    "Betrayal / revenge": rx([r"betray\w*", r"traitor\w*", r"revenge", r"justice", r"judge", r"punish\w*", r"pay for", r"regret", r"destroy\w*",
                              r"avenge\w*", r"verdict", r"guilty", r"liar\w*", r"lied", r"deceiv\w+"]),
}

# staging of a cliffhanger in camera/action text: freeze on a face/eye/object while something dreadful lands
CLIFF_REACT = rx([r"extreme close-?up", r"macro", r"holding (?:on|until)", r"lingering", r"wide(?:ning)? eyes?", r"wide,? (?:terrified|unblinking)",
                  r"terrif\w+", r"horrif\w+", r"realiz\w+", r"realisation", r"dread", r"bulging", r"disbelief", r"drained of (?:all )?colou?r",
                  r"abrupt\w*", r"suddenly", r"stifl\w+", r"stumbl\w+", r"recoil\w*", r"gasp\w*", r"trap", r"lethal", r"inches (?:from|of)",
                  r"stares? (?:at|into)", r"unblinking", r"frozen", r"paraly\w+", r"shock\w*", r"bewilder\w+"])

# ---------------------------------------------------------------------------------------------
# Story-intelligence lexicons (v2)
# ---------------------------------------------------------------------------------------------
TITLE_ROLES = r"(?:duke|duchess|king|queen|prince|princess|heir|emperor|ceo|billionaire|tycoon|general|commander)"
# identity / survival / culprit / truth ASSERTIONS. A line that ends in '?' is a QUESTION (curiosity), not a disclosure.
REVEAL_PATTERNS = [
    ("identity", re.compile(r"\b(?:you(?:'re| are)|he(?:'s| is)|she(?:'s| is)|they(?:'re| are)|i am|i'm)\s+(?:really\s+|truly\s+|actually\s+|still\s+)?(?:the\s+|a\s+|an\s+|your\s+|my\s+|our\s+|his\s+|her\s+)?(?:\w+\s+){0,2}" + TITLE_ROLES + r"\b", re.I)),
    ("identity", re.compile(r"\b(?:rightful|true|real|lost|hidden|secret|long-lost)\s+" + TITLE_ROLES + r"\b", re.I)),
    ("secret", re.compile(r"\b(?:real|true)\s+(?:name|identity|self)\b|\bsecret identity\b", re.I)),
    ("survival", re.compile(r"\b(?:you(?:'re| are)|he(?:'s| is)|she(?:'s| is)|they(?:'re| are))\s+(?:still\s+|really\s+)?alive\b|\bnot dead\b|\bstill alive\b|\bcame back from the dead\b|\bnever (?:died|dead)\b", re.I)),
    ("culprit", re.compile(r"\b(?:it was (?:you|him|her|them|your)|you (?:poisoned|killed|betrayed|murdered|tortured|framed|sold)|(?:poisoned|killed|betrayed|murdered|framed)\s+(?:me|him|her|my|our)|i (?:poisoned|killed|betrayed|framed)|behind (?:it all|this))\b", re.I)),
    ("secret", re.compile(r"\b(?:the truth (?:is|about)|i have been lying|i lied to you|all along|never (?:told|knew)|secretly|she is not|he is not|you are not)\b", re.I)),
]
TEASE_PATTERN = re.compile(r"\b(?:dead|late|lost|missing)\s+" + TITLE_ROLES + r"\b.*\b(?:coming home|returns?|returned|is back|has come|will return|alive)\b|\b(?:coming home|is coming|will return)\b", re.I)
GENERIC_Q = re.compile(r"^\W*(?:what(?:'s| is| was)?(?: happened| that| this| it| going on)?|who(?:'s| is| was)?(?: there| that| it)?|why|how|where)\W*$|^\W*what (?:happened|is that|was that|is this|is going on)\W*$", re.I)
DANGER_VISUAL = re.compile(r"\b(?:fire|flames?|smoke|burn\w*|blood\w*|scream\w*|crash\w*|explo\w+|collaps\w+|glow|orange|smell of|body|corpse|knife|sword|dagger|poison\w*)\b", re.I)
ANSWER_OPEN = re.compile(r"^\W*(?:yes|no|because|it was|it is|it's|that's|i did|he did|she did|they did|my name|i am|i'm|we are|we're|after|before|tomorrow|tonight|never|always|nothing|nobody|no one)\b", re.I)

# emotional engines v2 (multi-label). Names are what an editor would say out loud.
ENGINES2 = {
    "Revenge": rx([r"revenge", r"avenge\w*", r"make (?:you|them|him|her) pay", r"will pay", r"regret", r"destroy\w*", r"payback", r"justice", r"punish\w*", r"vengeance", r"ruin\w*", r"fist of", r"balance the scale"]),
    "Romance": rx([r"kiss\w*", r"embrace\w*", r"lips", r"my wife", r"my husband", r"i love you", r"marry me", r"wedding night", r"hold me", r"bandage\w*", r"stay with me", r"beautiful", r"mine\b", r"my heart", r"touch (?:me|you)", r"closer"]),
    "Betrayal": rx([r"betray\w*", r"traitor\w*", r"lied\b", r"lies\b", r"liar\w*", r"you knew", r"behind my back", r"sold (?:me|us|her|him)", r"deceiv\w+", r"double-cross\w*", r"turned (?:on|against)", r"disown\w*"]),
    "Mystery": rx([r"secret\w*", r"who (?:are|is|sent|told|did)", r"what (?:are|is) (?:this|that|it)", r"the truth", r"mystery", r"hidden", r"scar\w*", r"ledger", r"ring\b", r"locket", r"evidence", r"missing", r"strange", r"unknown", r"clue", r"investigat\w+", r"symbol", r"letter"]),
    "Rescue / protector": rx([r"protect\w*", r"rescu\w+", r"defend\w*", r"behind me", r"step(?:s|ped)? (?:in|between|forward)", r"touch (?:her|him)", r"guards?\b", r"sword", r"blade", r"shield\w*", r"save\w*", r"intervene\w*", r"get out of (?:the|my) way", r"let (?:her|him) go", r"lethal"]),
    "Humiliation / status": rx([r"humiliat\w+", r"shame\w*", r"disgrace\w*", r"guests", r"crowd", r"before (?:everyone|all)", r"in front of", r"mock\w*", r"laugh\w* at", r"plain(?:ness)?", r"worthless", r"beggar", r"stripped", r"banish\w*", r"kneel\w*", r"servant", r"unworthy"]),
    "Identity reveal": rx([r"duke\b", r"identity", r"who are you", r"true (?:name|self)", r"rightful", r"heir\b", r"all along", r"alive\b", r"disguise\w*", r"mask\w*", r"impost\w+", r"you(?:'re| are) the", r"i am the"]),
    "Conspiracy / poison": rx([r"poison\w*", r"arsenic", r"antidote", r"plot\w*", r"conspir\w+", r"witch\w*", r"gallows", r"treason\w*", r"scheme\w*", r"trial", r"accus\w+", r"spy", r"informant", r"council", r"hang\w*", r"fabricat\w+", r"succession", r"papers"]),
}

# strict relationship words: tell a stranger HOW two people are connected (not mere honorifics)
REL_STRICT = rx([r"husband", r"wife", r"fianc\w+", r"sisters?", r"brothers?", r"mother", r"father", r"mom\b", r"dad\b", r"daughter", r"\bson\b", r"stepmother", r"stepsister",
                 r"duke\b", r"duchess", r"\bking\b", r"queen", r"prince\w*", r"soldier", r"veteran", r"master", r"servant", r"maid", r"boss", r"\bex-?\w+", r"bride", r"groom", r"heir\b",
                 r"widow", r"mistress", r"enemy", r"rival", r"traitor", r"your grace", r"my love", r"my daughter", r"my son", r"captain", r"general", r"healer", r"priest"])
