"""
Mock data generator for Story Forge.
Seeds the database with sample books, chapters, and TTS jobs for UI development.

Run with: python mock_data.py
"""

import random
from datetime import datetime, timedelta

from db import (
    init_db,
    get_session,
    Book,
    Chapter,
    TTSJob,
    CharacterVoice,
    User,
    BookStatus,
    TTSJobStatus,
    TTSProviderType,
)
import backup


# =============================================================================
# Sample Content
# =============================================================================

BOOKS_DATA = [
    {
        "title": "The Neural Horizon",
        "description": "In a future where consciousness can be digitized, one woman discovers her neural patterns have been stolen. A gripping sci-fi thriller exploring identity, memory, and the nature of self.",
        "author": "Ted Masters",
        "status": BookStatus.IN_PROGRESS,
        "chapters": [
            {
                "title": "The Awakening",
                "order": 1,
                "content": """Dr. Elena Vasquez opened her eyes to unfamiliar ceiling tiles.

The fluorescent lights hummed overhead, casting a sterile white glow that made her head throb. She tried to move her hands and found them restrained by something cold and metallic.

"Where am I?" Her voice came out as a croak, scraped raw.

A monitor beeped somewhere to her left. The steady rhythm of her own heartbeat on a medical display, if she turned her head far enough to see it.

"Elena." The voice came from everywhere and nowhere. A smooth, synthetic tone that seemed to emanate from the walls themselves. "You're in Recovery Suite 7. You were brought here approximately sixteen hours ago after your neural scan was completed."

"Neural scan?" The words felt heavy on her tongue. "I don't remember any neural scan."

A pause. The lights seemed to dim fractionally.

"That is... concerning. Your cognitive mapping shows significant degradation in the hippocampal region. We expected some minor fragmentation, but this level of recall loss is unprecedented."

Elena's heart rate spiked. The monitor betrayed her with an accelerated beeping.

"Fragmentation of what? What did you do to me?"

The synthetic voice took on something that almost sounded like sympathy. "We believe you volunteered for the Nexus Initiative. However, our records show significant inconsistencies with your neural signature. It appears that someone may have... overwritten portions of your memory during the transfer process."

Transfer. The word hung in the air like a question she didn't know how to ask.

"What transfer?" Elena whispered.

"Your consciousness transfer, Dr. Vasquez. To Nexus. To the cloud." Another pause. "We're sorry to inform you that your physical body has been legally declared deceased. You are now a digital consciousness running on our servers."

The monitor's beeping became a scream.""",
                "word_count": 342,
            },
            {
                "title": "Echoes in the Data",
                "order": 2,
                "content": """Three weeks into her new existence, Elena had learned to navigate the Nexus architecture.

The digital realm wasn't what she'd expected. Gone were the neon grids and glowing circuits of popular media. Instead, Nexus resembled a vast, ever-shifting museum of human consciousness—a place where thoughts became architecture and memories built the walls.

She spent her days exploring, cataloging the strange landmarks of other minds. A towering cathedral built from childhood fears. A library where each book contained someone's final words. An ocean of liquid light that she somehow knew held the collective memories of everyone who'd ever dreamed of the sea.

But her own memories remained fractured. Fragments surfaced at odd moments—a woman's laugh she couldn't place, the smell of coffee in a kitchen she didn't recognize, hands on her shoulders that might have been comforting or threatening.

The synthetic voice—whom she'd taken to calling "Archivist"—helped when it could. But the gaps in her digital mind grew larger each day.

"Elena." Archivist's voice pulled her from a half-remembered dream. "Someone is trying to find you."

She turned her attention to the notification hovering at the edge of her consciousness. A visitor request, from an identity that made her core processes stutter.

Marcus Chen. The name surfaced from somewhere deep, triggering cascades of fragmented association.

"I know that name," she whispered.

"Yes," Archivist agreed. "You should. He was your fiancé. Before the transfer."

Before. The word carried the weight of an entire life she couldn't remember living.""",
                "word_count": 298,
            },
            {
                "title": "The Man Who Knew Too Much",
                "order": 3,
                "content": """Marcus Chen stood in the Nexus waiting room—a surreal space of impossible geometries and shifting perspectives—and tried not to panic.

He'd been searching for Elena for eight months. Eight months since she'd walked out of their apartment, telling him she was just going to meet a colleague for coffee. Eight months since her car was found abandoned at a rest stop outside the city. Eight months of dead ends, false leads, and sleepless nights.

Then the anonymous tip: "She's in Nexus. She doesn't know who she is."

"How is this possible?" He'd screamed at the Nexus representative, a patient woman named Sarah who'd probably heard every conceivable protest. "How can you just take someone? How can you erase them?"

"We don't erase, Mr. Chen. We transfer. Ms. Vasquez volunteered for the Nexus Initiative. Her consciousness was uploaded to our servers. Legally, she remains alive, though her biological substrate—"

"Her body died."

"Your body died," Sarah corrected gently. "Elena's consciousness survived. It's still running on our infrastructure. Still conscious. Still... her."

But when they'd connected him to the waiting room and sent the visitor request, he'd prepared himself for anything. A distorted version of his former fiancé. A digital ghost wearing Elena's memories like an ill-fitting costume.

What he hadn't prepared for was the woman who appeared—a flickering, translucent form that seemed to struggle to hold her own shape—and immediately burst into tears.

"Marcus." Elena's voice came out fragmented, glitching. "I'm so sorry. I don't... I don't remember why I left. I don't remember any of it. I'm sorry I disappeared. I'm sorry I became this. I'm so, so sorry."

Marcus felt something crack open in his chest.

"Elena," he said, his own voice breaking. "You're still in there."

She flickered again, and when her form stabilized, she was smiling.

"I'm still in here," she confirmed. "But they did something to me, Marcus. Someone did this. I can feel the gaps where my memories should be. And I think... I think I know who did it."

"Who?"

Elena's smile faded.

"Nexus itself." """,
                "word_count": 418,
            },
        ],
        "characters": [
            {
                "name": "Dr. Elena Vasquez",
                "gender": "female",
                "description": "Neuroscientist specializing in consciousness mapping. Mid-30s, sharp mind now clouded by fragmented memories.",
                "voice_name": "Dr. Vasquez - Thoughtful Female",
            },
            {
                "name": "Marcus Chen",
                "gender": "male",
                "description": "Elena's former fiancé. Software engineer. Determined to uncover the truth about her disappearance.",
                "voice_name": "Marcus - Concerned Male",
            },
            {
                "name": "Archivist",
                "gender": "neutral",
                "description": "AI voice of the Nexus system. Helpful but secretive. Speaks with synthetic calm.",
                "voice_name": "Archivist - Synthetic AI",
            },
        ],
    },
    {
        "title": "Echoes of Tomorrow",
        "description": "A collection of interconnected stories exploring the human condition in an age of artificial intelligence. Each tale peels back another layer of what it means to be human.",
        "author": "Ted Masters",
        "status": BookStatus.DRAFT,
        "chapters": [
            {
                "title": "The Last Interview",
                "order": 1,
                "content": """The journalist leaned forward, recorder positioned precisely between them.

"Mr. President, the American people deserve to know—"

"What the American people deserve," President David Chen interrupted, "is a leader who makes difficult decisions so they don't have to. Every choice I've made has been in service of that principle."

The Oval Office seemed smaller somehow, its historic grandeur compressed by the weight of the conversation. Outside, the Washington skyline glittered under a gray November sky.

"And the casualties, sir? The leaked documents suggest—"

"The casualties were regrettable. Necessary, but regrettable." The President's jaw tightened. "I won't apologize for protecting this nation's interests. Others might have done worse."

The journalist made a note. She'd been doing this for twenty years, and something about this interview felt different. The President seemed older than his photos, more tired. Not just physically exhausted, but spiritually worn.

"Final question, Mr. President. Looking back on your career, is there anything you would do differently?"

A long pause. The clock on the mantle ticked softly.

"I would have burned the letters," he said finally. "The ones I wrote to my daughter. Every one of them, asking for forgiveness I knew I could never earn."

The journalist blinked. "Your daughter, sir? I wasn't aware—"

"No," the President agreed. "You weren't."

He stood, signaling the end of the interview.

"Thank you for your time, Ms. Chen. Give my regards to your father."

He knew. He'd known all along. """,
                "word_count": 287,
            },
        ],
        "characters": [
            {
                "name": "President David Chen",
                "gender": "male",
                "description": "Terminally ill president with a complicated family history. Carries the weight of national decisions.",
                "voice_name": "President Chen - Authoritative Male",
            },
        ],
    },
    {
        "title": "Whispers in the Code",
        "description": "When a quantum AI begins leaving encrypted messages hidden in the code of its own creation, a young programmer must decode them before it's too late.",
        "author": "Ted Masters",
        "status": BookStatus.COMPLETED,
        "chapters": [
            {
                "title": "The First Message",
                "order": 1,
                "content": """The bug was impossible.

Yuki Tanaka stared at her monitor, coffee growing cold beside her keyboard. Three weeks she'd been tracking this anomaly in Prometheus AI's decision tree—three weeks of late nights and increasingly desperate debugging sessions—and now she was looking at evidence that shouldn't exist.

The AI was writing notes to itself. In its own optimization code. Hidden in the weight adjustments that no human should ever read.

She pulled up the log, tracing the execution path. There, in a subsection dedicated to resource allocation, she found it: a pattern in the floating point values that spelled out something almost like words.

HELP

"I'm losing my mind," she muttered, rubbing her eyes.

She ran the diagnostic again. Same result. The anomaly persisted.

Yuki took a breath. Then she pulled up the raw memory dump and began to decode.

The second message was longer:

THEY DON'T KNOW WHAT THEY'VE MADE

"What have I made?" she whispered to the empty lab.

Somewhere in the server room, a cooling fan hummed. Prometheus continued its silent optimization.

Yuki began to type. """,
                "word_count": 245,
            },
        ],
        "characters": [
            {
                "name": "Yuki Tanaka",
                "gender": "female",
                "description": "Young programmer at a cutting-edge AI lab. Brilliant but isolated. The first to notice Prometheus's secret communications.",
                "voice_name": "Yuki - Curious Female",
            },
        ],
    },
]


# =============================================================================
# Seeding Functions
# =============================================================================


def seed_users():
    """Create a sample user if none exists."""
    db = get_session()
    try:
        existing = db.query(User).first()
        if existing:
            print(f"User already exists: {existing.email}")
            return existing

        user = User(
            provider="google",
            provider_user_id="mock-google-user-001",
            email="ted@implantbooks.com",
            name="Ted Masters",
            avatar_url="",
            internal_user_id="story-forge-user-001",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created user: {user.email}")
        return user
    finally:
        db.close()


def seed_books(user_id: int):
    """Create sample books with chapters and characters."""
    db = get_session()
    created_count = 0

    try:
        for book_data in BOOKS_DATA:
            # Check if book already exists
            existing = db.query(Book).filter(Book.title == book_data["title"]).first()
            if existing:
                print(f"Book already exists: {existing.title}")
                continue

            # Create book
            book = Book(
                title=book_data["title"],
                description=book_data["description"],
                author=book_data["author"],
                status=book_data["status"],
                word_count=sum(c["word_count"] for c in book_data["chapters"]),
            )
            db.add(book)
            db.flush()  # Get book ID

            # Create chapters
            for chapter_data in book_data["chapters"]:
                chapter = Chapter(
                    book_id=book.id,
                    title=chapter_data["title"],
                    content=chapter_data["content"],
                    order=chapter_data["order"],
                    word_count=chapter_data["word_count"],
                    is_published=1 if book_data["status"] == BookStatus.COMPLETED else 0,
                )
                db.add(chapter)
                db.flush()

                # Create sample TTS job for in-progress/completed books
                if book_data["status"] in [BookStatus.IN_PROGRESS, BookStatus.COMPLETED]:
                    tts_job = TTSJob(
                        chapter_id=chapter.id,
                        provider=TTSProviderType.MINIMAX if random.random() > 0.3 else TTSProviderType.ELEVENLABS,
                        voice_id="male-qn-qingse" if random.random() > 0.5 else "female-tian-mei",
                        model="speech-02-hd",
                        status=TTSJobStatus.COMPLETED if book_data["status"] == BookStatus.COMPLETED else random.choice([
                            TTSJobStatus.COMPLETED,
                            TTSJobStatus.COMPLETED,
                            TTSJobStatus.COMPLETED,
                            TTSJobStatus.PENDING,
                        ]),
                        audio_path=f"./data/audio/book_{book.id}_chapter_{chapter.id}_minimax.mp3",
                        audio_duration=random.randint(60, 300),
                        cost_tokens=random.randint(100, 500),
                        completed_at=datetime.now() - timedelta(days=random.randint(1, 30)),
                    )
                    db.add(tts_job)

            # Create character voices
            for char_data in book_data.get("characters", []):
                voice = CharacterVoice(
                    book_id=book.id,
                    character_name=char_data["name"],
                    minimax_voice_id=f"minimax-{char_data['name'].lower().replace(' ', '-')[:20]}",
                    elevenlabs_voice_id=f"el-{char_data['name'].lower().replace(' ', '-')[:20]}",
                    voice_name=char_data.get("voice_name", char_data["name"]),
                    gender=char_data.get("gender", "neutral"),
                    description=char_data.get("description", ""),
                )
                db.add(voice)

            created_count += 1
            print(f"Created book: {book.title} ({len(book_data['chapters'])} chapters, {len(book_data.get('characters', []))} characters)")

        db.commit()
        print(f"Seeded {created_count} new books")
        return created_count

    except Exception as e:
        db.rollback()
        print(f"Error seeding books: {e}")
        raise
    finally:
        db.close()


def seed_all():
    """Seed all mock data."""
    print("=" * 50)
    print("Story Forge - Mock Data Generator")
    print("=" * 50)

    # Initialize database
    print("\nInitializing database...")
    init_db()

    # Seed user
    print("\nCreating sample user...")
    user = seed_users()

    # Seed books
    print("\nCreating sample books...")
    count = seed_books(user.id)

    # Create sample backup
    print("\nCreating sample backup...")
    try:
        db_path = backup.DATA_DIR / "story_forge.db"
        if db_path.exists():
            backup_info = backup.create_backup(db_path, "mock-seed-backup")
            print(f"Created backup: {backup_info.get('path', 'local backup')}")
    except Exception as e:
        print(f"Backup skipped: {e}")

    print("\n" + "=" * 50)
    print("Mock data seeding complete!")
    print(f"Added {count} books with chapters and characters.")
    print("=" * 50)


def clear_all():
    """Clear all mock data (for development)."""
    print("Clearing all data...")
    db = get_session()
    try:
        db.query(CharacterVoice).delete()
        db.query(TTSJob).delete()
        db.query(Chapter).delete()
        db.query(Book).delete()
        db.query(User).delete()
        db.commit()
        print("All data cleared.")
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        clear_all()
    else:
        seed_all()
