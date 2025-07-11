from sqlalchemy.orm import Session
from ..models import Track, Release


def update_release_tracks_if_changed(
    db: Session, release: Release, incoming_tracks: list[tuple[str, int | None, int | None, int | None]]
) -> bool:
    existing_tracks = db.query(Track).filter(Track.ReleaseId == release.Id).all()
    existing_tuples = [(t.Title.strip(), t.Length, t.TrackNumber, t.DiscNumber) for t in existing_tracks]

    existing_tuples.sort(key=lambda x: (x[3] if x[3] is not None else 0, x[2] if x[2] is not None else 0, x[0]))
    incoming_tracks.sort(key=lambda x: (x[3] if x[3] is not None else 0, x[2] if x[2] is not None else 0, x[0]))


    if existing_tuples == incoming_tracks:
        return False

    db.query(Track).filter(Track.ReleaseId == release.Id).delete()

    for title, length, track_number, disc_number in incoming_tracks:
        track = Track(
            Title=title.strip(),
            Length=length,
            TrackNumber=track_number,
            DiscNumber=disc_number,
            SizeOnDisk=None,
            ReleaseId=release.Id,
        )
        db.add(track)

    release.TrackFileCount = len(incoming_tracks)
    db.add(release)
    return True
