import test from 'node:test';
import assert from 'node:assert/strict';
import {buildSourceInventory} from '../scripts/channel-sources.mjs';

test('groups alternate source slots with the main entry without publishing stream URLs', () => {
 const playlist = '#EXTM3U\n#EXTINF:-1 tvg-id="GMA" tvg-name="GMA" group-title="Entertainment" tvg-chno="110",GMA\nhttps://example.com/token-secret\n#EXTINF:-1 tvg-id="primary-source:gma:1" tvg-name="GMA Stream 2" group-title="Entertainment" tvg-chno="110.001",GMA Stream 2\nhttps://example.com/other\n#EXTINF:-1 tvg-id="additional:gma:one" tvg-name="GMA *" group-title="Entertainment" tvg-chno="110.002",GMA *\nhttps://example.com/token-secret\n#EXTINF:-1 tvg-id="primary-source:gma:2" tvg-name="Different Channel" group-title="Movies" tvg-chno="201",Different Channel\nhttps://example.com/other2\n';
 const inventory={entries:[{id:'primary-source:gma:1',parentName:'GMA',serverIndex:1},{id:'primary-source:gma:2',parentName:'GMA',serverIndex:2}]};
 const result=buildSourceInventory(playlist,inventory,[{playlist_tvg_id:'GMA',status:'mapped'}]);
 assert.equal(result.entries,4); assert.equal(result.groups.length,1);
 const g=result.groups.find(x=>x.name==='GMA'); assert.equal(g.entries.length,4);
 assert.deepEqual(g.entries.map(x=>x.sameLink),[true,false,false,true]);
 assert.equal(g.entries[1].listedUnder,'GMA'); assert.equal(g.entries[0].guide,true);
 assert.equal(g.entries[2].name,'Different Channel'); assert.equal(g.entries[2].category,'Movies');
 assert.ok(!JSON.stringify(result).includes('token-secret'));
});


test('NBA events are grouped under NBA TV as distinct broadcasts', () => {
 const text='#EXTM3U\n#EXTINF:-1 tvg-id="NBA TV" tvg-name="NBA TV",NBA TV\nhttps://example.com/nba\n#EXTINF:-1 tvg-id="primary-source:nbatv:1" tvg-name="NBA TV - 8:00am A vs B",NBA TV - 8:00am A vs B\nhttps://example.com/event\n';
 const inv={entries:[{id:'primary-source:nbatv:1',parentName:'NBA TV',serverIndex:1}]};
 const out=buildSourceInventory(text,inv);assert.equal(out.groups.length,1);assert.equal(out.groups[0].name,'NBA TV');assert.equal(out.groups[0].entries.length,2);assert.equal(out.groups[0].entries[1].sameLink,false);
});


test('reviewed CineMo PH alternate is grouped without grouping unreviewed feeds', () => {
 const text='#EXTM3U\n#EXTINF:-1 tvg-id="CineMo!" tvg-name="CineMo!",CineMo!\nhttps://example.com/1\n#EXTINF:-1 tvg-id="primary-source:cinemo:4" tvg-name="CineMo! PH Stream 2",CineMo! PH Stream 2\nhttps://example.com/2\n#EXTINF:-1 tvg-id="primary-source:cinemo:3" tvg-name="CineMo! PH",CineMo! PH\nhttps://example.com/3\n';
 const out=buildSourceInventory(text);assert.equal(out.groups.find(g=>g.name==='CineMo!').entries.length,2);assert.equal(out.groups.find(g=>g.name==='CineMo! PH').entries.length,1);
});


test('alternates of a renamed main source appear under its displayed name', () => {
 const text='#EXTM3U\n#EXTINF:-1 tvg-id="Sci Fi" tvg-name="Sci Fi",Sci Fi\nhttps://example.com/1\n#EXTINF:-1 tvg-id="primary-source:syfy:1" tvg-name="SyFy 2",SyFy 2\nhttps://example.com/2\n';
 const out=buildSourceInventory(text,{entries:[{id:'primary-source:syfy:1',parentName:'SYFY',serverIndex:1}]});assert.equal(out.groups.length,1);assert.equal(out.groups[0].name,'Sci Fi');assert.equal(out.groups[0].entries.length,2);
});
