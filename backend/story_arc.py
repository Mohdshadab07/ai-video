"""Five-beat triangle arc: every clip keeps Aryan + Sara + Rohan in frame (~2 minutes when stitched).

Update existing rows by ``scene_number`` (1–5). ``veo3_prompt`` base length is tuned for longer Veo clips
(configure ``VEO_DURATION_SECONDS`` in ``.env``; try 24s × 5 ≈ 2 minutes)."""

from typing import Any

TWO_MINUTE_TRIANGLE_REV: list[dict[str, Any]] = [
    {
        "scene_number": 1,
        "title": "Rain Against the Glass",
        "location": "INT. Coffee shop",
        "time_of_day": "Evening storm",
        "action_text": "Sara centered at a narrow table between Aryan and Rohan; rain slashes the street behind them. Phones face down like a treaty. Cups steam. Silence pulls tight until Rohan lifts his eyes.",
        "dialogue_json": [
            {
                "speaker": "Rohan",
                "line": "You called us together. Finish the sentence you started weeks ago.",
                "note": "Measured, dangerously calm.",
            },
            {
                "speaker": "Sara",
                "line": "I kept both of you alive in my ribs and called it fairness.",
                "note": "Low, ashamed.",
            },
            {
                "speaker": "Aryan",
                "line": "I don't need poems. I need the truth inside the apology.",
                "note": "Restrained ache.",
            },
            {
                "speaker": "Rohan",
                "line": "Then let it land now — no rain checks, no half promises.",
                "note": "Unflinching.",
            },
            {
                "speaker": "Sara",
                "line": "Standing still felt kinder than choosing. I'm done being kind.",
                "note": "Voice steadies.",
            },
        ],
        "emotion_tags": ["Triangle", "Confession-light", "Pressure"],
        "veo3_prompt": (
            "Photoreal cinematic Indian drama, evening coffee shop beside rain-streaked window. "
            "THREE people ALWAYS visible sharing one small table — woman Sara center frame, calm man "
            "Aryan on camera left soft blue tones, bolder man Rohan on camera right earthy green-grey coat. "
            "Slow creeping dolly in over ~24 uninterrupted seconds of subtle blocking: hands twitch near phones, "
            "breathing visible under warm practical lights vs cool rain blues. Emotional stalemate cracking. "
            "No cartoon faces, textured skin and fabric, shallow depth-of-field cinema glass."
        ),
    },
    {
        "scene_number": 2,
        "title": "City Edge",
        "location": "EXT. Rooftop",
        "time_of_day": "Deep blue hour",
        "action_text": "Wind lifts scarves and shirt collars — all three at the parapet skyline glow. Nobody turns away; they face the ache head-on.",
        "dialogue_json": [
            {
                "speaker": "Aryan",
                "line": "If you disappear into him, swear you won't haunt me politely.",
                "note": "Bitter tenderness.",
            },
            {
                "speaker": "Rohan",
                "line": "If she stays with you, I'll leave without shredding her name.",
                "note": "Pride scraped raw.",
            },
            {
                "speaker": "Sara",
                "line": "You both turned love into siege lines. I've been waving a white cloth no one reads.",
                "note": "Loud whisper over wind.",
            },
            {
                "speaker": "Aryan",
                "line": "We read it. We're just terrified it's not for us anymore.",
                "note": "Confession slips out.",
            },
            {
                "speaker": "Rohan",
                "line": "Then walk us off this roof honestly — whoever she picks, breathe first.",
                "note": "Urgent empathy.",
            },
        ],
        "emotion_tags": ["Skyline ache", "Moral glare", "Courage spike"],
        "veo3_prompt": (
            "Photoreal nighttime Mumbai-style rooftop panorama. THREE leads visible together along railing — "
            "Sara centered backlit by city bokeh, Aryan silhouette left quieter posture, Rohan right steadier chin. "
            "Slow drifting handheld without chaos, crane-height feel, teal-orange grade, gusts tug hair/cloth over "
            "~24 continuous seconds. Emotional standoff blooming into fragile honesty."
        ),
    },
    {
        "scene_number": 3,
        "title": "Letters on the Marble",
        "location": "INT. Corridor outside lifts",
        "time_of_day": "Past midnight",
        "action_text": "Fluorescence hum — Sara pinned between both men beside closed lift doors — envelope in her palms trembling.",
        "dialogue_json": [
            {
                "speaker": "Sara",
                "line": "There's a resignation letter drafted twice with two different endings.",
                "note": "Voice thin.",
            },
            {
                "speaker": "Aryan",
                "line": "Read the cruel one aloud. Secrets rot slower when spoken.",
                "note": "Bleeding honor.",
            },
            {
                "speaker": "Rohan",
                "line": "If it ends with exile, carve my name cleanly — no maybe footnotes.",
                "note": "Determined softness.",
            },
            {
                "speaker": "Sara",
                "line": "Both endings bleed the same confession: I'm done borrowing courage.",
                "note": "Eyes brim.",
            },
            {
                "speaker": "Aryan",
                "line": "Then sign it with your chest unclenched. We'll survive the handwriting.",
                "note": "Gentled promise.",
            },
        ],
        "emotion_tags": ["Confession-heavy", "Exhaust", "Honor"],
        "veo3_prompt": (
            "Photoreal cramped apartment corridor, sterile lights. THREE characters tight triangle — Sara between "
            "Aryan (softer blazer) and Rohan (warm knit). Hovering handheld micro-moves ~24 seconds, envelope "
            "white-hot focus, cinematic shadows slicing faces, escalating intimacy minus melodrama slam."
        ),
    },
    {
        "scene_number": 4,
        "title": "Monsoon Interlude",
        "location": "EXT. Covered promenade",
        "time_of_day": "Thunder rolling",
        "action_text": "Sheets of rain veil the city — Sara steps between sprinting umbrellas flanked by both men like reluctant bodyguards learning détente.",
        "dialogue_json": [
            {
                "speaker": "Rohan",
                "line": "If this storm washes us backward, swear we meet without blades drawn.",
                "note": "Shouting over rain echoes.",
            },
            {
                "speaker": "Aryan",
                "line": "Blades dull when her laugh doesn't pick sides anymore.",
                "note": "Half-smile drowned by worry.",
            },
            {
                "speaker": "Sara",
                "line": "I want rehearsals over — whoever stays, whoever leaves, daylight next.",
                "note": "Fierce plea.",
            },
            {
                "speaker": "Aryan",
                "line": "Then don't vanish mid-sentence chasing fog.",
                "note": "Gravel honesty.",
            },
            {
                "speaker": "Rohan",
                "line": "We hear you. Feet firm. Hearts loud. Rain can't drown both.",
                "note": "Rally vow.",
            },
        ],
        "emotion_tags": ["Weather theatre", "Truce sparks", "Forward motion"],
        "veo3_prompt": (
            "Photoreal monsoon-covered arcade, rain curtains behind iron columns. Trio walking camera backward — "
            "Sara between Aryan and Rohan soaked shoulders, umbrellas abandoned, teal reflective puddles, "
            "slow wide-to-medium arc ~24 seconds, melodrama withheld in favor of quiet epic rain-soaked pact."
        ),
    },
    {
        "scene_number": 5,
        "title": "Courtyard Sunrise",
        "location": "EXT. Quiet courtyard",
        "time_of_day": "Pink dawn breaking",
        "action_text": "Birdsong thin — Sara plants herself equidistant in warm dust-light; both men step in so the triangle resolves open instead of trapping.",
        "dialogue_json": [
            {
                "speaker": "Sara",
                "line": "Love bloomed twice and I watered both while starving myself honesty.",
                "note": "Steadily breaking.",
            },
            {
                "speaker": "Aryan",
                "line": "Then feed yourself truth now — whisper who you become without apology.",
                "note": "Gentle command.",
            },
            {
                "speaker": "Rohan",
                "line": "We become witnesses if you'll walk forward without shackles.",
                "note": "Respectful uplift.",
            },
            {
                "speaker": "Sara",
                "line": "I'm choosing sunrise over scorecards — whoever stays owes me fearless mornings.",
                "note": "Resolute tenderness.",
            },
            {
                "speaker": "Aryan",
                "line": "Mornings owed. Breath shared. Roads parallel if not joined.",
                "note": "Open-hearted.",
            },
            {
                "speaker": "Rohan",
                "line": "Parallel still counts braver than vanishing ghosts.",
                "note": "Smile bittersweet.",
            },
        ],
        "emotion_tags": ["Closure-light", "Dawn pact", "Self-truth"],
        "veo3_prompt": (
            "Photoreal Indian courtyard sunrise, rose-gold backlight through neem foliage. Sara center equidistant, "
            "Aryan camera left halo soft, Rohan camera right bolder dawn rim. Trio breathes visibly in sync as camera "
            "orbits lazily ~24 seconds; texture-rich fabric, dusty beams, restrained tears, emotional finale without "
            "melodramatic yell — prestige TV drama pacing."
        ),
    },
]
