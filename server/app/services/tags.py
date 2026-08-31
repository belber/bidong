from sqlalchemy.orm import Session

from ..models import Tag


def get_or_create_tag(db: Session, user_id: int, name: str) -> Tag:
    name = name.strip()
    tag = db.query(Tag).filter(Tag.user_id == user_id, Tag.name == name).first()
    if tag is None:
        tag = Tag(user_id=user_id, name=name)
        db.add(tag)
        db.flush()
    return tag

