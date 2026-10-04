import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';

// Layout is verified in the visible browser. Protect the sizing constraints
// that prevent the ninth form cell shrinking into the narrow Source track.
const css=readFileSync(new URL('../src/components/PlanningPanel.css',import.meta.url),'utf8');
const dom=new JSDOM(`<style>${css.replace(/@media[^{}]*\{(?:[^{}]*\{[^{}]*\})*\}/g,'')}</style><div class="planning-form"><label>Source</label><button class="calculate-plan">Calculate Plan</button></div>`);
const form=dom.window.getComputedStyle(dom.window.document.querySelector('.planning-form'));
const action=dom.window.getComputedStyle(dom.window.document.querySelector('button'));
assert.equal(form.gridTemplateColumns,'repeat(auto-fit,minmax(min(140px,100%),1fr))');
assert.equal(action.minWidth,'140px');
assert.equal(action.gridColumn,'auto');
dom.window.close();
console.log('PASS: planner workspace tracks retain usable minimum sizing and action width');
