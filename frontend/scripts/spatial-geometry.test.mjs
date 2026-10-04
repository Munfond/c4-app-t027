import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import { reconstructSpatialSurfaces } from '../src/lib/viewer/spatial-surfaces.ts';
import { SpatialObjectFactory, objectForm } from '../src/lib/viewer/spatial-objects.ts';

const detection = (className, size = { width:.7,length:.75,height:1.8 }) => ({
  id:'object', className, center:{forward:0,left:0,up:size.height/2}, size,
  yawRadians:0,velocity:{forward:0,left:0},confidence:.9,
});

test('missing and invalid returns do not create terrain or buildings', () => {
  const result = reconstructSpatialSurfaces([[NaN,0,0],[1,2],[0,0,0],[10,5,4]],[]);
  assert.equal(Object.values(result.groups).reduce((sum,points)=>sum+points.length,0),2);
  assert.equal(result.facades.length,0);
  const empty = reconstructSpatialSurfaces([],[]);
  assert.equal(empty.groundVertices.length,0);
  assert.equal(empty.facades.length,0);
  // The one observed floor cell cannot stretch toward the isolated return.
  for(let i=0;i<result.groundVertices.length;i+=3) {
    assert(result.groundVertices[i]>=-1 && result.groundVertices[i]<=0);
    assert(result.groundVertices[i+2]>=-1 && result.groundVertices[i+2]<=0);
  }
});

test('facade patches stay on a measured planar surface and exclude detected objects', () => {
  const ground = Array.from({length:100},(_,i)=>[i%10,Math.floor(i/10),0]);
  const wall=[];for(let x=30;x<38;x+=.3) for(let z=.6;z<4;z+=.3) wall.push([x,6,z]);
  const result = reconstructSpatialSurfaces([...ground,...wall],[]);
  assert(result.facades.length>0);
  for(const patch of result.facades) {
    assert(Math.abs(patch.left-6)<.001);
    assert(patch.forward>=30 && patch.forward<=38);
    assert(patch.bottom>=.6 && patch.bottom+patch.height<=4);
    assert(Object.values(patch).every(Number.isFinite));
  }
  const box={...detection('other',{width:5,length:12,height:5}),center:{forward:34,left:6,up:2}};
  assert.equal(reconstructSpatialSurfaces([...ground,...wall],[box]).facades.length,0);
});

test('person and car silhouettes stay inside the predicted dimensions', () => {
  const factory=new SpatialObjectFactory();
  for(const d of [detection('pedestrian'),detection('car',{width:1.9,length:4.5,height:1.6}),detection('traffic_cone',{width:.4,length:.4,height:.8})]) {
    const root=factory.create(d,'#81d2ce'),bounds=new THREE.Box3().setFromObject(root),epsilon=.03;
    assert(bounds.min.y>=-epsilon && bounds.max.y<=d.size.height+epsilon);
    assert(bounds.min.x>=-d.size.width/2-epsilon && bounds.max.x<=d.size.width/2+epsilon);
    assert(bounds.min.z>=-d.size.length/2-epsilon && bounds.max.z<=d.size.length/2+epsilon);
  }
  const d={...detection('car',{width:1.9,length:4.5,height:1.6}),center:{forward:12,left:-4,up:.8},yawRadians:1.2};
  const root=factory.create(d,'#81d2ce');
  assert.deepEqual(root.position.toArray(),[4,0,-12]);
  assert.equal(root.rotation.y,1.2);
  assert.equal(objectForm('traffic_cone'),'other');
  factory.dispose();
});
