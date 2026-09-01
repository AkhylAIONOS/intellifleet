import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: [
      "unprecipitate-liquidly-randal.ngrok-free.dev",
      "prostrative-gnawingly-kelli.ngrok-free.dev",
      "20.244.15.92:15484",
      "intellifleet.hirenowx.com",
      "tunes-driven-floyd-recorder.trycloudflare.com",
      "value-pepper-icq-lindsay.trycloudflare.com",
      "webshots-invited-receptors-brand.trycloudflare.com",
      "thrush-wired-directly.ngrok-free.app",
      "headers-nest-obtain-nurse.trycloudflare.com",
      "sharon-permit-selected-performs.trycloudflare.com"
    ]
  }
})
