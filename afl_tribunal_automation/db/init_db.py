"""Create all tables. Run with: python -m db.init_db"""

from db.models import Base, engine


def main() -> None:
    Base.metadata.create_all(engine)
    print("Tables created.")


if __name__ == "__main__":
    main()
