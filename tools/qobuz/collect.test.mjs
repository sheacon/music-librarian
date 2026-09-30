import test from 'node:test';
import assert from 'node:assert/strict';
import {pages} from './collect.mjs';

test('paginates past the first 100 and tolerates duplicate releases', async () => {
  let offsets = [];
  const get = async (_, params) => {
    offsets.push(params.offset);
    return {albums: params.offset === 0 ? {total:102,items:Array.from({length:100},(_,i)=>({id:String(i+1)}))} : {total:102,items:[{id:'100'},{id:'101'}]}};
  };
  const result = await pages(get,'artist/get','albums',{});
  assert.equal(result.length,101);
  assert.deepEqual(offsets,[0,100]);
});

test('fails if the API repeats an entire page', async () => {
  const get = async () => ({albums:{total:200,items:[{id:'1'}]}});
  await assert.rejects(pages(get,'artist/get','albums',{}), /Repeated/);
});

test('fails rather than treating missing results as an empty library', async () => {
  await assert.rejects(pages(async () => ({albums:{total:1,items:[]}}),'x','albums',{}), /Incomplete/);
});

test('classifies candidates and older matching editions only', async () => {
  const {classifyCandidates} = await import('./collect.mjs');
  const items = [
    {id:'new',title:'Work',artist:{id:1},release_date_original:'2026-09-25'},
    {id:'old',title:'Work (Deluxe)',artist:{id:1},release_date_original:'2020-01-01'},
    {id:'other',title:'Other',artist:{id:1},release_date_original:'2020-01-01'}
  ];
  const calls=[];
  await classifyCandidates(async (_,p)=>{calls.push(p.album_id);return {id:p.album_id,release_type:p.album_id==='old'?'single':'album'};},items,'2026-09-23','2026-09-30');
  assert.deepEqual(calls.sort(),['new','old']);
  assert.equal(items[0].release_type,'album');
  assert.equal(items[1].release_type,'single');
});
