<!--
HANDOVER NOTE FOR THE REPORT DESIGNER

This markdown is the full content for a minimal internship project report on
"Nucleus". It is written in plain English in the intern's own voice. Please
format it into a clean, minimal report: a title page, a table of contents, and
then each section on its own. Keep the wording as it is. Tables should stay as
tables. Nothing here needs to reach the internet.
-->

# Nucleus
### An Offline-First, Privacy-Preserving AI Assistant for Combat and Disaster Response

**Internship Project Report**
Prepared by: Prince Trivedi
Project: Nucleus
Reporting period: Week 1 to Week 9

---

## Table of Contents

1. Introduction
2. Objectives
3. Tools and Technologies
4. System Architecture
5. Weekly Progress
   - Week 1
   - Week 2
   - Week 3
   - Week 4
   - Week 5
   - Week 6
   - Week 7
   - Week 8
   - Week 9
6. Current Status
7. Remaining Work
8. Conclusion

---

## 1. Introduction

Nucleus is an offline-first AI assistant built for soldiers, combat medics, and disaster response teams such as the NDRF. It gives them quick, practical answers for tactical and medical situations, helps them classify casualties, and builds a standard medical evacuation request. It also helps them find the nearest hospital or evacuation point on a map that works with no internet.

The whole project is built around one hard rule. A person in the field should be able to use a powerful AI without that AI ever learning who they are, where they are, or which unit they belong to. If the device is captured, it should give up nothing. If there is no signal, the important features should still work.

The system uses a cloud AI model for its reasoning, because a small model on a field tablet is not good enough for real medical decisions. To make that safe, every request passes through a privacy layer on the device that removes identifying details before anything is sent, and puts the real details back only on the device after the answer returns. Everything stored on the device is encrypted, and the map runs entirely on local data.

---

## 2. Objectives

The project is built to meet the following clear goals. Each one is something the system can actually be shown doing, not just a promise.

1. No personally identifying data reaches any outside service. Names, service numbers, grid coordinates, callsigns, unit names, and radio frequencies are removed from every request before it leaves the device.
2. The soldier still gets an accurate and useful answer. Removing the identifying details must not lower the quality of the medical or tactical advice.
3. Every critical function works with no internet connection. Triage, medical evacuation, and map lookups all have a working offline path.
4. A captured device gives up nothing. All stored data is encrypted, and one action can make it permanently unrecoverable.
5. Life-safety output is never a single guess. The nine line evacuation request is built from several independent answers, and any part they disagree on is flagged for a human to check.
6. The system is honest about its own limits. It says when an answer came from local cache, when a distance is straight line and not road distance, when a map point is unverified, and when it is unsure.

---

## 3. Tools and Technologies

| Layer | Technology | Why it was chosen |
|---|---|---|
| Backend framework | FastAPI (Python) | Light and fast, with automatic checking of request shapes. Good for a small field service. |
| Frontend | React with Vite | Quick to develop, and its component style suits the chat, map, and side panel layout. |
| AI model | Google Gemini (Flash and Pro tiers) | Strong medical reasoning without the heavy computing a local model would need on a tablet. |
| Structured output | Pydantic schemas with strict JSON | Forces the model to return a fixed shape. This removes parsing errors and reduces made-up answers. |
| At-rest encryption | XChaCha20-Poly1305 | Modern and fast on tablets that have no hardware acceleration for older ciphers. |
| Key derivation | Argon2id (libsodium) | Needs a lot of memory to compute, which makes a captured device very hard to brute force. |
| Client storage | Encrypted IndexedDB in the browser | Stays on the device. No server process and no network port to attack. |
| Local semantic search | MiniLM through transformers.js | Turns chat messages into vectors inside the browser, offline after one download. |
| Offline maps | MapLibre GL with MBTiles vector tiles | Self-hosted map tiles with no outside map request. |
| Facility search | SQLite R\*Tree spatial index | Nearest-facility lookup with no extra dependencies and no network. |
| Geodesy | MGRS to and from latitude and longitude, haversine distance | Operators speak in MGRS grids and the nine line carries a grid. |

---

## 4. System Architecture

The design keeps sensitive work on the device and sends only cleaned, tokenized facts to the cloud when the cloud is used at all.

```
   [ Device / Browser ]
     Chat, Triage, Mass Casualty, Map, MEDEVAC button
        |
        |  chat is indexed locally (MiniLM vectors)
        |  everything is stored in encrypted IndexedDB
        |
        v
   [ Local Backend ]
     Privacy layer: replace names, grids, callsigns with tokens,
       and add calibrated noise to sensitive numbers (differential privacy)
     Maps: intent detection, facility search, distance, all on-device
        |
        |  only tokenized facts leave, over TLS
        v
   [ Gemini in the cloud ]
     Reads tokens like [NAME_1] and [GRID_1], never real values
        |
        v
   [ Local Backend ]
     Put the real values back (only on the device)
        |
        v
   [ Device / Browser ]
     Operator sees the real answer. Cloud never did.
```

Two rules hold everywhere. First, there is only one path to the network, so the privacy step cannot be skipped by accident. Second, if the cloud cannot be reached, every important feature falls back to a local answer built from data on the device.

---

## 5. Weekly Progress

### Week 1 [ May 18 to May 22, 2026 ]

I started by working out the core design and setting up the project. I chose FastAPI for the backend because it is light and fast, and React for the frontend.

The first focus was the medical and military logic. I studied the triage categories, from Immediate down to Expectant, and set up the data shapes for the standard protocols so the system knows how to handle different injuries.

I built the nine line medical evacuation generator. I wrote the logic that takes basic inputs such as grid coordinates, patient type, and security status, and turns them into a correctly formatted radio message.

I then started on a local database to hold digital Casualty Cards in place of paper forms. Because this is a field tool, storing patient names and unit details in plain text is a serious risk if the device is captured. I researched local encryption and decided to use Fernet, and I drafted a plan for a privacy pipeline that would encrypt sensitive fields before they touch the disk.

I also made an early architecture decision. I moved away from training small local models, which struggled with real medical reasoning and needed too much computing power, and decided to use the Gemini cloud model instead. To keep that safe, I began designing a privacy gateway, and I planned a differential privacy step using the Laplace method so that sensitive numbers such as age or weight could be protected before they leave.

Finally, I connected a basic React frontend to the backend so I had a working screen to type injuries into and check the nine line output.

### Week 2 [ May 23 to May 29, 2026 ]

Sir, Week 2 was about one question. How do you give a soldier a powerful AI without that AI ever seeing who they are, where they are, or what unit they are from.

I built a privacy step that sits between the soldier's input and the cloud call. It does three things in order. First, it generalises rather than deletes. A grid reference becomes a general location and a unit name becomes a general unit, so the medical picture stays clear but nothing identifying leaves. Second, it adds Laplace noise to numbers such as ages and distances, so the value is close enough to be useful but the exact figure cannot be recovered. Third, a content check runs before anything is sent, and anything marked classified is blocked at the edge. After the model answers, the response is checked again and anything that leaked through is removed.

All of this runs with a local encrypted cache. The first time a question is asked it goes through the full pipeline. The next time the same question is asked, the answer comes back instantly from the device with no cloud call at all, which also acts as a simple rate limit.

For speed, I sent general questions to the faster Gemini tier and kept the stronger tier for triage where accuracy matters most. I also capped general answers at a short length, because field answers should be short and easy to read under stress. The chat screen for this was finished, with small indicators that show what happened to the data.

### Week 3 [ June 1 to June 5, 2026 ]

Sir, this week was mostly about removing things. In a field tool, every extra feature is also an extra risk, so I cut the system back to what it actually needs.

**Removing the drug interaction checker**

I removed the drug interaction checker completely, including its page, routes, and backend code. It was never part of the approved plan, and it added risk and stored data for no real benefit.

**Removing casualty tracking, and why**

The bigger decision was removing the casualty tracking feature and the digital Casualty Cards from Week 1. This reverses my own earlier design, so I want to explain it. Encrypting a casualty database protects the data only as long as the encryption holds. Not storing casualty identities at all protects the data no matter what. If the database was never written, there is nothing for a captured device to give up. I decided the strongest guarantee is the one where the data does not exist.

So Nucleus no longer stores who was affected. Mass casualty events are still handled fully. The system gives prioritisation guidance for the whole incident, meaning how to sort casualties, which to move first, and how to use the medics and supplies, but it never records any single person.

**Result**

The interface now has three clear modes, which is closer to how a medic thinks under pressure. General Query, Triage, and Mass Casualty. A useful side effect is that the backend now stores nothing at all, which shaped the storage decision I made later.

### Week 4 [ June 8 to June 12, 2026 ]

Sir, the AI layer from Week 1 was one large file doing every job. This week I rebuilt it as a proper service layer, and while testing it I found a real limit in the free Gemini tier.

**Splitting the AI layer**

I split the one big file into small files, each with one job. There is a shared client that does the actual generation, a key manager, one file for all the prompts, and one service file each for general queries, triage, mass casualty, and evacuation. Now I can improve the medical wording without touching the request handling.

**Forcing strict JSON**

Every call now returns strict JSON that matches a fixed shape. This removed a whole class of parsing failures, and it reduces made-up answers because the model cannot write anything unexpected in a field that is limited to the four triage categories.

**Key rotation, and the free tier problem**

I built a key manager that loads many API keys and moves to the next one when a key hits its rate limit. During testing, every call to the stronger model failed. It turned out that on the free tier, that model has a quota of zero, so no key rotation can help. I restructured the retry logic so that it first tries the primary model across every key, and if that fails everywhere, it falls back to the faster model. In the field, a slightly weaker answer is much better than no answer.

### Week 5 [ June 15 to June 19, 2026 ]

Sir, this was the most important week so far. While building the evacuation generator, I found a flaw in the privacy idea from Week 2 and rebuilt it.

**The flaw in generalisation**

The Week 2 step replaced a grid with the phrase "a general location". But line one of a nine line evacuation request is the grid coordinate. A pickup request that says "a general location" is useless. Generalisation buys privacy by destroying the exact information the soldier needs back.

**Reversible tokenisation**

So I replaced it. Each identifier is now swapped for a numbered token, and the link between the token and the real value is kept in memory on the device, only for that one request. The cloud sees "[GRID_1]", the medic sees the real grid. The medical part of the sentence is never touched, so accuracy does not drop. It recognises ten kinds of identifier, and it uses fixed rules rather than a model, because for a field tool I need to prove that the grid was removed every time.

**Two privacy problems, two tools**

I understood that the project faces two different problems, and that both need to run in the same pipeline. Direct identifiers such as names and grids must be removed exactly, and adding noise to a name means nothing. That is what the tokenisation layer handles. Exact numbers such as age and weight cannot just be deleted, because the AI needs them, but if they are left exact they can be used to identify a casualty. That is what the differential privacy layer handles, using the Laplace method to add calibrated noise to those numbers before they leave the device. The two run together. Tokenisation gives certainty on the identifiers, and differential privacy gives a measured limit on what the numbers that must survive can reveal.

**One path and full honesty**

I moved the privacy step inside the one function every service calls, so it cannot be skipped. Every response now reports which kinds of identifier were removed and shows the exact text that left the device, so the soldier can read the proof rather than trust a claim.

### Week 6 [ June 22 to June 26, 2026 ]

Sir, Week 5 protected data while it travels. This week protected data while it sits on the device, and finished the evacuation button.

**Upgrading the encryption**

I reviewed the Week 1 choice and replaced it. I moved the cipher to XChaCha20-Poly1305, which also checks the data has not been changed and is fast on tablets without special hardware. I moved key derivation to Argon2id, which needs a lot of memory and so is hard to brute force on a captured device. I replaced the old secure wipe, which overwrote the file three times, because that is not reliable on flash storage. Now a hard wipe deletes the key, and after that any leftover data is permanently unreadable.

**Reversing the database choice**

In Week 2 I planned to use a cloud PostgreSQL database. After removing all server side storage, I looked again and reversed it. A running database is a separate process with a network port and log files that can hold plain text. For a single device that stores nothing on the server, that is extra risk for no benefit. Storage now stays on the device in an encrypted browser database.

**On-device search and the evacuation button**

Every message is turned into a vector inside the browser, and those vectors are encrypted too, because a vector still carries the meaning of the text. When the medic presses Generate Medical Evacuation, the system finds the most relevant messages, sends only that small slice after cleaning it, and never sends the whole chat.

**Consensus voting with PromptPATE**

This part draws on PromptPATE from our privacy research. The idea behind it is that you never trust a single model on its own, you take the agreed answer of an ensemble, because agreement across many is a much stronger signal than the confidence of one. I applied that same idea to the nine line. The generator now asks the model for several independent versions and takes a majority vote on each line. Where the versions agree, confidence is high. Where they disagree, the line is marked for a human to check rather than guessed. This turns a hidden risk into a number the medic can see, and it puts the PromptPATE mechanism to work as a reliability layer in the pipeline.

**Offline fallback**

If the cloud cannot be reached, the button still works. It fills a fixed template from the chat and defaults to the most urgent category when severity is unclear, because over-triage is the safer mistake.

### Week 7 [ June 29 to July 3, 2026 ]

Sir, this week I started the offline map. A medic often needs the nearest hospital or helipad, but a normal maps service would send the position to a company server and also give off a signal. Both break the whole point of the project, so the map has to run on the device.

**Map tiles from OpenStreetMap**

I set up offline map tiles built from OpenStreetMap and packed into a single file. The backend serves them, and the browser draws them with a map library. Nothing is loaded from the internet, not even the map fonts. A soldier can pan and zoom the map with the radio off.

**Grids, distance, and direction**

Operators speak in MGRS grids, so I wrote the maths to convert between a grid and latitude and longitude, and to work out the distance and the compass direction between two points. I used straight line distance on purpose. It is within the error of a normal GPS fix, so a more expensive calculation would not help. I also chose not to show a travel time, because a straight line distance divided by a guessed speed only looks like a real time and is not one. A missing time is a fact the operator can act on. A made up time is not.

**Finding the nearest facility quickly**

I built a spatial index over the hospitals, clinics, and helipads from the map data, so finding the nearest one is fast and needs no network. The search first narrows to a small box around the operator and then measures the exact distance to rank the results.

**Deciding when the chat needs a map**

Not every question needs a map, so I wrote a local rule to decide. It needs both a nearness word and a facility word. "Where is the entry wound" does not open a map, because there is no facility. "Where is the nearest hospital" does. This runs on the device with nothing sent out, which is also why it works offline.

**Checking it works**

I added a status page that shows what map data is installed, and I confirmed that asking for the nearest hospital to a grid returns the distance and direction with no network at all.

### Week 8 [ July 6 to July 10, 2026 ]

Sir, this week I made the map smart and connected it into the whole app.

**The brain in the cloud, the hands on the device**

The local rule from Week 7 catches clear questions like "nearest hospital", but it misses questions like "my guy took shrapnel and we are pinned, where is the closest place we can treat him". So I gave the cloud model one extra job in the same call it already makes. From the cleaned, tokenised text, it decides whether a map would help and which kinds of facility to show. It never sees a coordinate. The device then adds the real position, which never left it, and finds the actual facilities from the local index. The model decides the kind of help, and the device does the part that needs the real location.

**The operator's own places, kept secret**

An operator can mark a place, such as an evacuation point they set up. That is intelligence about their own area, so every operator pin, including its coordinates, is encrypted before it is written to the disk, and it is removed by the wipe. The public map data is not encrypted, because it is public and hiding it would protect nothing.

**Always showing where a place came from**

A surveyed hospital and one soldier's pin are very different levels of trust. Every result says which it is, and an operator pin is clearly marked as unverified, so a medic never mistakes one person's note for confirmed map data.

**Wiring the map into every mode**

The map can now open from the general chat, from triage when the nearest surgical care matters for an urgent casualty, from mass casualty for staging, and from the evacuation button, which plots the casualty and the nearest evacuation points.

**Keeping the privacy promise on map answers**

When the cloud model is used to phrase a map answer, the facility names are turned into tokens as well, so real names do not leave. If the model mentions a place that was not on the list it was given, the whole answer is thrown away and the local template is used instead, because a made up place could send a casualty to nowhere. A time limit stops a bad connection from hanging the request, and the local answer, which is already ready, wins.

**Checking it works**

I confirmed the map opens from a natural question through the cloud decision, that an operator pin can be added and read back, and that the offline template answer works when the cloud is switched off.

### Week 9 [ July 13 to July 17, 2026 ]

Sir, this week was about checking the whole project carefully and finishing it.

**A full review pass**

I ran a detailed review over the whole codebase, looking for every kind of problem, including wrong logic, edge cases, and repeated or dead code. It found a set of real issues. The main ones were a place where the chat context ranking mixed two different scoring scales, a case where a broken map index would return a server error instead of falling back cleanly, two small map edge cases near the map boundary, and some leftover code from an old design. I fixed the important ones and noted the rest.

**Cleaning up**

I removed the old single file engine that the new service layer had already replaced. I also sorted out which files belong in version control and which are runtime files or personal notes that should not be tracked.

**Checking the whole thing runs**

I confirmed that the backend starts cleanly, the frontend builds, and the main paths all work when tested live. This included the private query path with the identifiers removed and put back, the evacuation path with the consensus vote, the offline fallback with the cloud switched off, and the map path.

**Where the project stands**

The core is complete and working. The layered privacy pipeline, meaning reversible tokenisation for identifiers, differential privacy for sensitive numbers, and the PromptPATE consensus for the evacuation output, is in place together with the encryption, the three chat modes, the evacuation generator, and the offline map. The honest next steps are a set of automated tests, a road routing engine to give real travel distances, and bundling a small map region so a demo is fully offline from the start.

---

## 6. Current Status

The following parts are built and have been tested live.

- Three chat modes: general query, triage, and mass casualty.
- A layered privacy pipeline that works on every request. Reversible tokenisation removes direct identifiers and puts them back only on the device, differential privacy using the Laplace method protects sensitive numbers such as age and weight, and the operator can see a proof of exactly what was sent.
- A PromptPATE consensus that protects the reliability of the evacuation output by voting across several independent answers and flagging any part the answers disagree on.
- Model routing that uses a fast tier for general questions and a stronger tier for triage, with automatic fallback when a tier is unavailable.
- A nine line medical evacuation generator that uses a consensus vote for reliability and falls back to a fully offline template with no internet.
- On-device encryption using XChaCha20-Poly1305 with an Argon2id key, a soft wipe that clears data, and a hard wipe that destroys the key so nothing can be recovered.
- An offline map with local tiles, nearest-facility search, encrypted operator pins, and a smart option where the cloud model decides if a map helps without ever seeing a location.

---

## 7. Remaining Work

- Automated tests for the privacy round trip, the grid conversion, the map intent detection, the consensus vote, and the encryption.
- A road routing engine to replace straight line distance with real travel distance and time, as part of a later live tracking phase.
- Bundling the small local search model and one map region so the app is fully offline on a fresh device.
- Aligning the server side pin encryption with the newer client side encryption.

---

## 8. Conclusion

Nucleus set out to answer one difficult question. Can a soldier or a disaster responder use a powerful AI without giving up their identity, their location, or their unit, and without depending on a signal that may not be there. Over nine weeks the project grew from a single chat screen into a working system that removes identifying data before it leaves the device, keeps everything encrypted at rest, generates a checked medical evacuation request, and finds the nearest help on a map that runs with the radio off.

The most valuable lessons were the reversals. Removing the casualty database made the data safer than any encryption could. Replacing generalisation with reversible tokens kept the privacy without losing the accuracy. Each change came from testing a real case and finding that the earlier idea did not hold. The result is a system that is honest about what it does, that protects the person using it, and that keeps working when it is needed most.
