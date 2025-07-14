# Releasarr

<p align="center">
  <img src="/logo/cover.png" alt="Releasarr Cover" width="600" />
</p>
<p align="center">
  <img src="/logo/artist.png" alt="Artist Page" width="600" />
</p>

---

## Overview

**Releasarr** is a music release monitoring and management tool designed to help you keep track of your favorite artists and their releases. It integrates multiple music platforms and services to provide a unified view of your music collection and new releases.

### Key Features

- Monitor artists and manage your music collection.
- View detailed release information.
- Track external music platform IDs (Deezer, Discogs, Spotify, MusicBrainz).
- Add, edit, and delete artists, releases, and tracks.
- Simple and clean user interface.
- Integration with SABnzbd and Usenet indexers for enhanced automation.

---

## Installation & Usage

´´´yaml
services:
  Releasarr:
    image: makario1337/releasarr:latest
    ports:
      - "127.0.0.1:1337:1337"
    volumes:
      - ./config:/config
    environment:
      APP_PORT: 1337
      APP_WORKERS: 4
    container_name: releasarr
    restart: unless-stopped
```

```bash
docker run -d \
  --name=releasarr \
  -e APP_PORT=1377 \
  -e APP_WORKERS=4 \
  -p 127.0.0.1:1337:1337 \
  -e ./config:/config
  --restart unless-stopped \
  makario1337/releasarr:latest
```

---

## Planned Features

- SABnzbd integration  
- Usenet indexers  
- Notifications using [Apprise](https://github.com/caronc/apprise)  
- Track editing, deleting, and viewing  
- Release editing, deleting, and viewing  
- More customizable settings  
- Possibly dark mode  
- Spotify metadata synchronization  
- Track tagging  
- File actions (e.g., storage and artist path management)  

> **Note:** The software is currently in development and **not yet ready for production use**.

---

## Disclaimer & Usage Notice

This software is provided **“as is”**, without any warranties or guarantees of any kind, either express or implied. Use it at your own risk. The author is not responsible for any damage or issues arising from the use of this software.

**Important:**  
Releasarr does **not** condone or promote piracy or illegal distribution of copyrighted material.  
Please use this software responsibly and respect artists’ rights.

---

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0).

You are free to share and adapt this project **for non-commercial purposes only**, as long as you provide proper attribution.

See the [LICENSE](LICENSE) file for details.

---

## Attribution

Icons provided by [Simple Icons](https://simpleicons.org/) and [Font Awesome](https://fontawesome.com/), both under their respective free licenses.