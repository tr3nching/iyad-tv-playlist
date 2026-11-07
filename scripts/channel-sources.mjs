import { readFile, writeFile } from 'node:fs/promises';

const decode = value => value.replace(/&(amp|quot|lt|gt);/g, (_, key) => ({amp:'&',quot:'"',lt:'<',gt:'>'}[key]));
const attr = (line, name) => decode(line.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] || '');
const key = name => name.replace(/\s*\*\s*$/, '').replace(/\s+Stream\s+\d+$/i, '').toLocaleLowerCase('en').replace(/[^a-z0-9]/g, '');

// Names suggest a relationship, not verified program, language, or regional identity.
export function buildSourceInventory(playlist, inventory = {}, mappings = []) {
  const sources = new Map((inventory.entries || []).map(row => [row.id, row]));
  const guides = new Map(mappings.map(row => [row.playlist_tvg_id, row.status === 'mapped']));
  const groups = new Map();
  const byUrl = new Map();
  for (const block of playlist.split(/(?=^#EXTINF:)/m).slice(1)) {
    const line = block.split(/\r?\n/)[0];
    const id = attr(line, 'tvg-id');
    if (!id || id.startsWith('category:')) continue;
    const name = attr(line, 'tvg-name');
    const url = block.split(/\r?\n/).find(row => /^https?:\/\//.test(row));
    if (!url) continue;
    const source = sources.get(id);
    const entry = {name, number: attr(line, 'tvg-chno'), category: attr(line, 'group-title'),
      kind: id.startsWith('additional:') ? 'additional' : source ? 'alternate' : 'primary',
      ...(source ? {listedUnder: source.parentName, sourceSlot: source.serverIndex} : {}),
      guide: guides.has(id) ? guides.get(id) : null, sameLink: false};
    // NBA event slots share a navigation group; they are separate broadcasts.
    const nbaEvent = source?.parentName === 'NBA TV' && /^NBA TV - \d{1,2}:\d{2}\s*(?:am|pm)\s+.+\s+vs\.?\s+.+/i.test(name);
    const groupKey = nbaEvent ? key('NBA TV') : key(name);
    if (!groups.has(groupKey)) groups.set(groupKey, {name: nbaEvent ? 'NBA TV' : name.replace(/\s*\*\s*$/, '').replace(/\s+Stream\s+\d+$/i, ''), entries: []});
    groups.get(groupKey).entries.push(entry);
    if (!byUrl.has(url)) byUrl.set(url, []);
    byUrl.get(url).push(entry);
  }
  for (const matches of byUrl.values()) if (matches.length > 1) for (const entry of matches) entry.sameLink = true;
  const list = [...groups.values()].sort((a,b) => a.name.localeCompare(b.name, 'en', {sensitivity:'base',numeric:true}));
  return {updatedAt: new Date().toISOString(), entries: list.reduce((n,g)=>n+g.entries.length,0), groups: list};
}

export async function writeSourceInventory(site) {
  const readJson = async name => { try {return JSON.parse(await readFile(new URL(name, site), 'utf8'));} catch(error) {if(error.code==='ENOENT') return undefined; throw error;} };
  const playlist = await readFile(new URL('playlist.m3u', site), 'utf8');
  const report = buildSourceInventory(playlist, await readJson('primary-source-catalog.json'), await readJson('mapping.json'));
  await writeFile(new URL('channel-sources.json', site), JSON.stringify(report, null, 2)+'\n');
}
