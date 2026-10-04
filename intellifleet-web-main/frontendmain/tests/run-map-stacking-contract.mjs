import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const css=readFileSync(new URL('../src/components/MapView.css',import.meta.url),'utf8');
const dom=new JSDOM(`<style>${css}</style><div class="map-view"><div class="leaflet-container"></div></div>`);
assert.equal(dom.window.getComputedStyle(dom.window.document.querySelector('.map-view')).isolation,'isolate');
assert.equal(dom.window.getComputedStyle(dom.window.document.querySelector('.leaflet-container')).height,'100%');
dom.window.close();
console.log('PASS: Leaflet controls have a local stacking context without changing map sizing');
