# Releasarr
[![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white&style=flat-square)](https://github.com/Makario1337/Releasarr)
[![Discord Server](https://img.shields.io/badge/Discord-7289da?logo=discord&logoColor=white&style=flat-square)](https://discord.gg/bv98atxBJT)
[![Docker Hub](https://img.shields.io/badge/Docker_Hub-2496ED?logo=docker&logoColor=white&style=flat-square)](https://hub.docker.com/r/makario1337/releasarr)


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

## Planned Features

> **Note:** The software is currently in development and **not yet ready for production use**.

- [ ] [SABnzbd](https://github.com/sabnzbd/sabnzbd) (and possibly NZBGet) integration  
- [ ] Torrent client support  
- [X] Integrated Deemix downloader  
- [ ] Indexer support via [Prowlarr](https://github.com/Prowlarr/Prowlarr)  
- [ ] Notification system using [Apprise](https://github.com/caronc/apprise)  
- [ ] Track management (view, edit, delete)  
- [ ] Enhanced settings and customization options  
- [ ] Optional dark mode  
- [ ] Multiple metadata sources (~~Deezer~~, MusicBrainz, Spotify, Discogs)  
- [ ] Audio track tagging support  
- [ ] File management (e.g., artist path control, storage handling)

---

## Installation & Usage
### docker-compose (recommended)

```yaml
---
services:
  Releasarr:
    image: makario1337/releasarr:latest
    ports:
      - "127.0.0.1:1337:1337"
    volumes:
      - ./config:/config
      - ./logs:/logs
      - ./library:/library
    environment:
      APP_PORT: 1337
      APP_WORKERS: 4
    container_name: releasarr
    restart: unless-stopped
```

### docker cli

```bash
docker run -d \
  --name=releasarr \
  -e APP_PORT=1377 \
  -e APP_WORKERS=4 \
  -p 127.0.0.1:1337:1337 \
  -e ./config:/config \
  -e ./logs:/logs \
  -e ./library:/library \
  --restart unless-stopped \
  makario1337/releasarr:latest
```

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

SABnzbd Icon from [here](https://github.com/sabnzbd/sabnzbd)