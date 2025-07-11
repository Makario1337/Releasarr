from sqlalchemy.orm import Session
from ..models import Release, Track

def update_release_tracks_if_changed(db: Session, release: Release, incoming_tracks_data: list[dict]) -> bool:

    changes_made = False

    incoming_tracks_data.sort(key=lambda x: (
        x.get("DiscNumber", 0) if x.get("DiscNumber") is not None else 0,
        x.get("TrackNumber", 0) if x.get("TrackNumber") is not None else 0,
        x.get("Title", "")
    ))

    existing_tracks = db.query(Track).filter(Track.ReleaseId == release.Id).all()
    existing_tracks.sort(key=lambda x: (
        x.DiscNumber if x.DiscNumber is not None else 0,
        x.TrackNumber if x.TrackNumber is not None else 0,
        x.Title
    ))


    existing_tracks_comparable = [
        {
            "Title": t.Title,
            "Duration": t.Duration,
            "TrackNumber": t.TrackNumber,
            "DiscNumber": t.DiscNumber
        }
        for t in existing_tracks
    ]

    if len(incoming_tracks_data) != len(existing_tracks_comparable) or \
       any(inc != ex for inc, ex in zip(incoming_tracks_data, existing_tracks_comparable)):
        
        changes_made = True
        
        for track in existing_tracks:
            db.delete(track)
        
        for track_data in incoming_tracks_data:
            new_track = Track(
                ReleaseId=release.Id,
                Title=track_data.get("Title"),
                Duration=track_data.get("Duration"),
                TrackNumber=track_data.get("TrackNumber"),
                DiscNumber=track_data.get("DiscNumber")
            )
            db.add(new_track)
        
        release.TrackFileCount = len(incoming_tracks_data)
        db.add(release)
    return changes_made

