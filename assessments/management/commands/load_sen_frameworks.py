"""
Load pre-built SEN assessment framework templates.

Frameworks included:
  - EYFS (Early Years Foundation Stage)
  - Engagement Model (DfE statutory 2021)
  - Pre-Key Stage Standards
  - National Curriculum (adapted)
  - B Squared
  - Equals Semi-Formal / Informal
  - Routes for Learning
  - Cherry Garden Curriculum

Usage:
  python manage.py load_sen_frameworks            # load all
  python manage.py load_sen_frameworks --only eyfs engagement_model
  python manage.py load_sen_frameworks --list      # show available names
"""

from django.core.management.base import BaseCommand

from assessments.models import AssessmentArea, AssessmentFramework, AssessmentStatement
from students.models import Subject


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ensure_subject(name, short=""):
    obj, _ = Subject.objects.get_or_create(
        name=name,
        defaults={"short_name": short, "is_active": True},
    )
    return obj


def _load_framework(name, description, areas_data):
    """
    areas_data: list of dicts:
      {
        "subject": "English",          # Subject name
        "subject_short": "Eng",        # optional short name
        "area": "Area Name",
        "year_group": None,            # optional int
        "phase": None,                 # optional int
        "statements": ["stmt1", "stmt2", ...]
      }
    """
    fw, created = AssessmentFramework.objects.get_or_create(
        name=name,
        defaults={"description": description, "is_active": True},
    )
    if not created:
        # already exists — skip to avoid duplicating statements
        return fw, False

    area_order = 0
    for ad in areas_data:
        subj = _ensure_subject(ad["subject"], ad.get("subject_short", ""))
        area_order += 1
        area = AssessmentArea.objects.create(
            framework=fw,
            subject=subj,
            name=ad["area"],
            year_group=ad.get("year_group"),
            phase=ad.get("phase"),
            order=area_order,
        )
        for idx, stmt_text in enumerate(ad["statements"], start=1):
            AssessmentStatement.objects.create(
                area=area,
                statement_text=stmt_text,
                order=idx,
            )
    return fw, True


# ---------------------------------------------------------------------------
# Framework definitions
# ---------------------------------------------------------------------------

def _eyfs():
    """EYFS — Early Years Foundation Stage (Development Matters 2021)."""
    common_subj = "EYFS"
    common_short = "EYFS"
    areas = [
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Communication and Language",
            "statements": [
                "Listens and pays attention in a range of situations",
                "Understands and follows simple instructions",
                "Responds to what they have heard with relevant comments, questions or actions",
                "Uses language to imagine and recreate roles and experiences in play",
                "Speaks in sentences using a growing range of vocabulary",
                "Expresses ideas and feelings about their experiences",
                "Listens to and joins in with stories and poems, one-to-one and in a small group",
                "Joins in with repeated refrains and anticipates key events and phrases",
                "Begins to be aware of the way stories are structured",
                "Describes events in some detail",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Physical Development",
            "statements": [
                "Moves freely and with pleasure and confidence in a range of ways",
                "Mounts stairs, steps or climbing equipment using alternate feet",
                "Shows increasing control over an object in pushing, patting and throwing",
                "Uses simple tools to effect changes to materials",
                "Handles tools, objects, construction and malleable materials with increasing control",
                "Shows a preference for a dominant hand",
                "Begins to use anticlockwise movement and retrace vertical lines",
                "Begins to form recognisable letters",
                "Understands importance of exercise, healthy eating, sleep and hygiene",
                "Manages own basic hygiene and personal needs, including dressing and toileting",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Personal, Social and Emotional Development",
            "statements": [
                "Is confident to try new activities and shows independence",
                "Plays co-operatively, taking turns with others",
                "Takes account of one another's ideas about how to organise their activity",
                "Shows sensitivity to others' needs and feelings",
                "Forms positive relationships with adults and other children",
                "Explains own knowledge and understanding, and asks appropriate questions",
                "Understands and follows rules",
                "Adjusts behaviour to different situations and takes changes of routine in stride",
                "Aware of boundaries set and behavioural expectations in the setting",
                "Talks about feelings and can manage some impulses and strong emotions",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Literacy",
            "statements": [
                "Enjoys rhyming and rhythmic activities",
                "Shows awareness of rhyme and alliteration",
                "Recognises rhythm in spoken words",
                "Hears and says the initial sound in words",
                "Links sounds to letters, naming and sounding the letters of the alphabet",
                "Uses some clearly identifiable letters to communicate meaning",
                "Writes own name and other things such as labels and captions",
                "Begins to read words and simple sentences",
                "Enjoys an increasing range of books",
                "Knows information can be retrieved from books and computers",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Mathematics",
            "statements": [
                "Recites numbers in order to 10 and beyond",
                "Counts objects using 1:1 correspondence",
                "Recognises numerals 1 to 10 and beyond",
                "Selects the correct numeral to represent 1 to 5 objects",
                "Uses the language of 'more' and 'fewer' to compare two sets of objects",
                "Finds one more or one less from a group of up to 5 objects",
                "Begins to use mathematical names for 2D and 3D shapes",
                "Uses positional language (e.g. in front, behind, next to)",
                "Orders and sequences familiar events",
                "Measures short periods of time in simple ways",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Understanding the World",
            "statements": [
                "Talks about past and present events in their own lives and the lives of family members",
                "Knows about similarities and differences between themselves, others and communities",
                "Knows about similarities and differences in relation to places, objects, materials and living things",
                "Talks about the features of their own immediate environment and how it differs from others",
                "Makes observations of animals, plants and explains why some things occur",
                "Experiments to find out how things work",
                "Completes a simple program on a computer",
                "Uses ICT hardware to interact with age-appropriate software",
                "Shows care and concern for living things and the environment",
                "Shows interest in different occupations and ways of life",
            ],
        },
        {
            "subject": common_subj, "subject_short": common_short,
            "area": "Expressive Arts and Design",
            "statements": [
                "Explores and uses media and materials",
                "Sings songs, makes music and dances, and experiments with ways of changing them",
                "Safely uses and explores a variety of materials, tools and techniques",
                "Experiments with colour, design, texture, form and function",
                "Uses what they have learnt about media and materials in original ways",
                "Represents their own ideas, thoughts and feelings through design, music, dance, role play and stories",
                "Constructs with a purpose in mind, using a variety of resources",
                "Selects appropriate resources and adapts work where necessary",
                "Creates simple representations of events, people and objects",
                "Introduces a storyline or narrative into their play",
            ],
        },
    ]
    return _load_framework(
        "EYFS (Early Years Foundation Stage)",
        "Development Matters 2021 — 7 areas of learning for early years.",
        areas,
    )


def _engagement_model():
    """Engagement Model (DfE statutory 2021) — 5 areas."""
    subj = "Personal Development"
    areas = [
        {
            "subject": subj, "subject_short": "PD",
            "area": "Exploration",
            "statements": [
                "Shows interest in or curiosity about people, objects or events",
                "Reaches out towards people, objects or events",
                "Touches, mouths or manipulates objects with interest",
                "Takes part in shared exploration of objects and events",
                "Encounters new experiences willingly",
                "Directs attention towards people, objects or events",
                "Shows anticipation of familiar events or activities",
            ],
        },
        {
            "subject": subj, "subject_short": "PD",
            "area": "Realisation",
            "statements": [
                "Demonstrates a change in behaviour following encounter with a stimulus",
                "Shows understanding that their actions lead to a result",
                "Demonstrates awareness of cause and effect",
                "Shows a 'lightbulb moment' or surprise in response to discovery",
                "Applies a previously learned behaviour in a new context",
                "Demonstrates consolidation of a skill or understanding",
            ],
        },
        {
            "subject": subj, "subject_short": "PD",
            "area": "Anticipation",
            "statements": [
                "Looks, turns or moves in the direction of an expected event",
                "Shows expectation that a familiar routine will happen next",
                "Responds appropriately in anticipation of an activity or event",
                "Vocalises or gestures in anticipation of a preferred stimulus",
                "Demonstrates prediction of what happens next",
                "Anticipates the outcome of an action before it occurs",
            ],
        },
        {
            "subject": subj, "subject_short": "PD",
            "area": "Persistence",
            "statements": [
                "Continues to engage with a task despite difficulty or challenge",
                "Returns to an activity after a break or interruption",
                "Sustains attention on a task for an increasing period",
                "Repeats actions to achieve a desired result",
                "Tries different approaches when the first attempt does not work",
                "Maintains effort over time to complete a multi-step task",
            ],
        },
        {
            "subject": subj, "subject_short": "PD",
            "area": "Initiation",
            "statements": [
                "Makes spontaneous requests or choices",
                "Starts an activity or interaction without being directed",
                "Makes independent choices about what to do",
                "Leads an activity or interaction with others",
                "Initiates communication to express needs or preferences",
                "Takes the first step in a sequence of actions independently",
            ],
        },
    ]
    return _load_framework(
        "Engagement Model",
        "DfE statutory framework (2021) — 5 engagement areas for pupils "
        "working below the level of the national curriculum and not engaged "
        "in subject-specific study.",
        areas,
    )


def _pre_key_stage():
    """Pre-Key Stage Standards (DfE) — English, Maths, Science."""
    areas = []
    # English
    for label, stmts in [
        ("PKS English — Listening & Attention", [
            "Pupils listen and attend to familiar people",
            "Pupils show understanding of single-element instructions",
            "Pupils understand and respond to two-element instructions",
            "Pupils follow narratives and descriptions with prompts",
        ]),
        ("PKS English — Speaking", [
            "Pupils communicate intentionally using vocalisations, gestures or symbols",
            "Pupils use single words or signs to express needs",
            "Pupils combine two key words or signs to communicate",
            "Pupils use phrases and simple sentences",
        ]),
        ("PKS English — Reading", [
            "Pupils engage with and enjoy listening to stories that are read to them",
            "Pupils pay attention to illustrations in books",
            "Pupils begin to recognise familiar printed words and symbols",
            "Pupils show awareness that text carries meaning",
        ]),
        ("PKS English — Writing", [
            "Pupils make marks with meaning",
            "Pupils copy letter shapes with support",
            "Pupils write or type some letters from their name",
            "Pupils write recognisable letters to communicate meaning",
        ]),
    ]:
        areas.append({
            "subject": "English", "subject_short": "Eng",
            "area": label,
            "statements": stmts,
        })

    # Maths
    for label, stmts in [
        ("PKS Mathematics — Number", [
            "Pupils show awareness of number in everyday activities",
            "Pupils rote count with some numbers in the correct order",
            "Pupils count objects reliably up to 5",
            "Pupils recognise and identify numerals up to 5",
        ]),
        ("PKS Mathematics — Shape, Space & Measure", [
            "Pupils show awareness of shape and size",
            "Pupils sort objects by a single criterion",
            "Pupils use simple positional language (e.g. on, under, next to)",
            "Pupils compare two quantities or measurements",
        ]),
    ]:
        areas.append({
            "subject": "Mathematics", "subject_short": "Maths",
            "area": label,
            "statements": stmts,
        })

    # Science
    areas.append({
        "subject": "Science", "subject_short": "Sci",
        "area": "PKS Science — Working Scientifically",
        "statements": [
            "Pupils respond to and show awareness of contrasting stimuli",
            "Pupils observe and communicate about changes in the immediate environment",
            "Pupils explore materials by sorting, grouping and describing simple properties",
            "Pupils show understanding of cause and effect in simple practical investigations",
        ],
    })

    return _load_framework(
        "Pre-Key Stage Standards",
        "DfE Pre-Key Stage Standards for pupils working below KS1/KS2 "
        "national curriculum expectations in English, Maths & Science.",
        areas,
    )


def _b_squared():
    """B Squared — broad SEN progression framework."""
    areas = []
    for label, stmts in [
        ("B Squared — Communication", [
            "Encounters — shows awareness of stimuli (visual, auditory, tactile)",
            "Awareness — attends to stimulus and sustains interest briefly",
            "Attention & Response — responds consistently to a range of stimuli",
            "Engagement — engages in back-and-forth interaction",
            "Participation — actively participates in activities with support",
            "Involvement — sustains involvement and contributes to activities",
            "Gaining Skills & Understanding — applies communication in new contexts",
        ]),
        ("B Squared — Cognition", [
            "Encounters — reacts to sensory input",
            "Awareness — demonstrates awareness of objects and people",
            "Attention & Response — focuses attention with support",
            "Engagement — explores and investigates",
            "Participation — participates in problem-solving with support",
            "Involvement — shows sustained focus and effort",
            "Gaining Skills & Understanding — applies learning across settings",
        ]),
        ("B Squared — Physical & Sensory", [
            "Encounters — tolerates sensory experiences",
            "Awareness — responds to sensory stimuli with preference",
            "Attention & Response — uses senses to explore",
            "Engagement — uses fine and gross motor skills with support",
            "Participation — participates in physical activities",
            "Involvement — shows increasing control and coordination",
            "Gaining Skills & Understanding — transfers skills to daily routines",
        ]),
        ("B Squared — PSHE & Citizenship", [
            "Encounters — shows awareness of others",
            "Awareness — recognises familiar people and routines",
            "Attention & Response — responds to social cues",
            "Engagement — interacts with others purposefully",
            "Participation — follows social rules with support",
            "Involvement — maintains relationships and takes responsibility",
            "Gaining Skills & Understanding — applies social skills independently",
        ]),
    ]:
        areas.append({
            "subject": "Personal Development", "subject_short": "PD",
            "area": label,
            "statements": stmts,
        })

    return _load_framework(
        "B Squared",
        "B Squared assessment progression framework for pupils with SEN — "
        "tracks small steps across Communication, Cognition, Physical/Sensory, "
        "and PSHE domains.",
        areas,
    )


def _equals():
    """Equals Semi-Formal & Informal Curriculum."""
    areas = []
    for label, stmts in [
        ("Equals — My Communication", [
            "Responds consistently to familiar people and cues",
            "Expresses preferences through vocalisation, gesture or symbol",
            "Engages in simple turn-taking interactions",
            "Uses a functional communication system to make requests",
            "Communicates for a range of purposes (request, reject, comment, greet)",
        ]),
        ("Equals — My Thinking", [
            "Explores objects and cause-and-effect toys",
            "Matches identical objects or images",
            "Sorts objects into simple categories",
            "Completes simple sequences and patterns",
            "Applies problem-solving strategies with support",
        ]),
        ("Equals — My Body & Movement", [
            "Tolerates a range of physical and sensory experiences",
            "Shows awareness of own body in space",
            "Uses fine motor skills to manipulate objects",
            "Participates in structured physical activities",
            "Demonstrates increasing physical independence",
        ]),
        ("Equals — My Creative Arts", [
            "Responds to music, art or sensory stimuli",
            "Explores different materials and media",
            "Makes marks, sounds or movements with intention",
            "Creates simple representations",
            "Expresses ideas through creative media",
        ]),
        ("Equals — My Independence", [
            "Tolerates adult support for personal care routines",
            "Participates actively in self-care tasks (eating, dressing, hygiene)",
            "Follows a visual schedule or routine with support",
            "Makes simple choices in daily life",
            "Demonstrates increasing independence in familiar routines",
        ]),
        ("Equals — My World", [
            "Shows awareness of the immediate environment",
            "Responds to changes in settings and routines",
            "Recognises familiar places and their purpose",
            "Shows understanding of their community (shops, transport, park)",
            "Demonstrates awareness of safety in different environments",
        ]),
    ]:
        areas.append({
            "subject": "Personal Development", "subject_short": "PD",
            "area": label,
            "statements": stmts,
        })

    return _load_framework(
        "Equals (Semi-Formal / Informal)",
        "Equals Semi-Formal and Informal Curriculum framework for pupils "
        "with PMLD/SLD — covers communication, thinking, physical, creative, "
        "independence and community.",
        areas,
    )


def _routes_for_learning():
    """Routes for Learning (Welsh Government) — augmented 43-step framework."""
    areas = []
    for label, stmts in [
        ("Routes for Learning — Early Communication", [
            "Shows awareness of people by becoming still, turning towards them",
            "Responds to familiar voice or touch",
            "Demonstrates anticipation of familiar routine",
            "Requests 'more' by vocalisation, movement or eye-gaze",
            "Takes turns in a simple interaction",
            "Makes a choice between two items when offered",
        ]),
        ("Routes for Learning — Early Cognition", [
            "Reacts to sensory stimuli (sound, light, texture)",
            "Fixates on or tracks an object",
            "Performs a single action to obtain a result (cause and effect)",
            "Searches briefly for a hidden object",
            "Shows object permanence — finds a partially hidden item",
            "Uses trial and improvement to solve a simple problem",
        ]),
        ("Routes for Learning — Early Physical Skills", [
            "Accepts being moved or repositioned",
            "Reaches towards or grasps an object",
            "Releases an object intentionally",
            "Transfers an object from one hand to the other",
            "Uses a purposeful whole-hand grasp (palmar)",
            "Uses a pincer grip or adapted grasp to pick up small items",
        ]),
    ]:
        areas.append({
            "subject": "Personal Development", "subject_short": "PD",
            "area": label,
            "statements": stmts,
        })

    return _load_framework(
        "Routes for Learning",
        "Routes for Learning framework (Welsh Government) — assessment steps "
        "for learners with profound and multiple learning difficulties (PMLD).",
        areas,
    )


def _cherry_garden():
    """Cherry Garden Curriculum — holistic SEN school framework."""
    areas = []
    for label, stmts in [
        ("Cherry Garden — Sensory Engagement", [
            "Encounters a range of sensory stimuli",
            "Shows preferences for particular sensory experiences",
            "Attends to and engages with sensory activities",
            "Uses sensory information to make sense of the environment",
            "Applies sensory strategies to support own regulation",
        ]),
        ("Cherry Garden — Communication & Interaction", [
            "Shows awareness of another person (by turning, stilling or vocalising)",
            "Engages in shared attention with an adult",
            "Uses intentional communication (vocalisation, eye-gaze, gesture)",
            "Takes part in interactive routines and turn-taking",
            "Communicates for a range of functions (request, reject, comment, share)",
        ]),
        ("Cherry Garden — Cognition & Problem Solving", [
            "Explores objects through mouthing, banging, shaking",
            "Demonstrates understanding of cause and effect",
            "Matches and sorts objects by type or property",
            "Shows anticipation based on previous experience",
            "Applies known strategies to new problems with support",
        ]),
        ("Cherry Garden — Physical & Self-Help", [
            "Tolerates physical handling and positioning changes",
            "Participates in gross motor activities with support",
            "Uses fine motor skills to interact with objects and materials",
            "Participates in self-care routines (eating, dressing, hygiene)",
            "Shows increasing independence in physical and self-care tasks",
        ]),
        ("Cherry Garden — Social & Emotional Wellbeing", [
            "Shows recognition of familiar people",
            "Engages in positive relationships with key adults",
            "Participates in group activities alongside peers",
            "Expresses emotions in contextually appropriate ways",
            "Demonstrates coping strategies for managing change or challenge",
        ]),
    ]:
        areas.append({
            "subject": "Personal Development", "subject_short": "PD",
            "area": label,
            "statements": stmts,
        })

    return _load_framework(
        "Cherry Garden Curriculum",
        "Cherry Garden holistic curriculum for special schools — tracks "
        "sensory engagement, communication, cognition, physical/self-help, "
        "and social-emotional wellbeing.",
        areas,
    )


def _national_curriculum():
    """National Curriculum — adapted core subjects with phase-based areas."""
    areas = [
        {
            "subject": "English", "subject_short": "Eng",
            "area": "Reading Phase 1",
            "phase": 1,
            "statements": [
                "I can read common words on sight",
                "I can use phonics to decode unfamiliar words",
                "I can retell a simple story in order",
                "I can answer simple questions about a text",
                "I can identify the main character in a story",
            ],
        },
        {
            "subject": "English", "subject_short": "Eng",
            "area": "Writing Phase 1",
            "phase": 1,
            "statements": [
                "I can form lowercase letters correctly",
                "I can write my own name",
                "I can write a simple sentence with a capital letter and full stop",
            ],
        },
        {
            "subject": "Mathematics", "subject_short": "Maths",
            "area": "Number Phase 1",
            "phase": 1,
            "statements": [
                "I can count to 10 reliably",
                "I can recognise numerals 1-10",
                "I can count backwards from 10",
                "I can add two single-digit numbers",
            ],
        },
    ]
    return _load_framework(
        "National Curriculum",
        "National Curriculum adapted framework — core subjects with "
        "phase-based assessment areas for schools tracking against "
        "national expectations.",
        areas,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FRAMEWORKS = {
    "eyfs": ("EYFS (Early Years Foundation Stage)", _eyfs),
    "engagement_model": ("Engagement Model (DfE 2021)", _engagement_model),
    "pre_key_stage": ("Pre-Key Stage Standards", _pre_key_stage),
    "national_curriculum": ("National Curriculum", _national_curriculum),
    "b_squared": ("B Squared", _b_squared),
    "equals": ("Equals Semi-Formal / Informal", _equals),
    "routes_for_learning": ("Routes for Learning", _routes_for_learning),
    "cherry_garden": ("Cherry Garden Curriculum", _cherry_garden),
}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Load pre-built SEN assessment framework templates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            nargs="+",
            metavar="KEY",
            help="Load only the specified framework(s) by key name.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_frameworks",
            help="List available framework keys and exit.",
        )

    def handle(self, *args, **options):
        if options["list_frameworks"]:
            self.stdout.write("Available frameworks:\n")
            for key, (label, _) in FRAMEWORKS.items():
                self.stdout.write(f"  {key:25s} — {label}")
            return

        keys = options.get("only") or list(FRAMEWORKS.keys())
        for key in keys:
            if key not in FRAMEWORKS:
                self.stderr.write(self.style.ERROR(f"Unknown framework key: {key}"))
                continue
            label, loader = FRAMEWORKS[key]
            fw, created = loader()
            if created:
                n_areas = fw.areas.count()
                n_stmts = AssessmentStatement.objects.filter(area__framework=fw).count()
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ {fw.name} — {n_areas} areas, {n_stmts} statements"
                ))
            else:
                self.stdout.write(f"  · {fw.name} — already exists, skipped")
