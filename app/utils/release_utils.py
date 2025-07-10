# app/utils/release_utils.py

from sqlalchemy.orm import Session
from ..models import Track, Release


def update_release_tracks_if_changed(
    db: Session, release: Release, incoming_tracks: list[tuple[str, int | None]]
) -> bool:
    """
    Compares existing tracks in DB with new track list.
    Updates only if there's a difference.

    Args:
        db (Session): SQLAlchemy session
        release (Release): The Release object to update
        incoming_tracks (list[tuple[str, int | None]]): List of (title, length) tracks

    Returns:
        bool: True if tracks were updated, False if no change
    """
    existing_tracks = db.query(Track).filter(Track.ReleaseId == release.Id).all()
    existing_tuples = [(t.Title.strip(), t.Length) for t in existing_tracks]

    if existing_tuples == incoming_tracks:
        return False  # No update needed

    db.query(Track).filter(Track.ReleaseId == release.Id).delete()

    for title, length in incoming_tracks:
        track = Track(
            Title=title.strip(),
            Length=length,
            SizeOnDisk=None,
            ReleaseId=release.Id,
        )
        db.add(track)

    release.TrackFileCount = len(incoming_tracks)
    db.add(release)
    return True
