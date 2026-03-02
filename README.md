# xfinity-device-tracker

something i'm building to help keep track of devices on my local network.
this works with my gateway, so your mileage may vary. that said, it's a standard Xfinity gateway (modem/wireless router combo unit) (Model:TG1682G) running a simple web ui.
---
requirements:
 - python (version?)
 - pip
   - see requirements.txt

---
to run:
 - run backend api with: uvicorn api:app --host 0.0.0.0 --port 8000
 - run frontend web ui with: [coming soon]