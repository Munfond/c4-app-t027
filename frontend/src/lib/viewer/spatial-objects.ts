import * as THREE from "three";
import type { ViewerDetection } from "./types";

export type ObjectForm = "vehicle" | "person" | "other";
export function objectForm(name: string): ObjectForm {
  const label = name.toLowerCase();
  if (label === "car" || label.endsWith(".car")) return "vehicle";
  if (label === "pedestrian" || label.startsWith("human.pedestrian")) return "person";
  return "other";
}

/** Shared primitive resources; root groups always retain the measured box transform. */
export class SpatialObjectFactory {
  private readonly box = new THREE.BoxGeometry(1, 1, 1);
  private readonly sphere = new THREE.SphereGeometry(1, 12, 8);
  private readonly cylinder = new THREE.CylinderGeometry(1, 1, 1, 12);
  private readonly capsule = new THREE.CapsuleGeometry(1, 1, 3, 8);
  private readonly cabin: THREE.BufferGeometry;
  private readonly glass = new THREE.MeshLambertMaterial({ color: "#1e3542" });
  private readonly tyre = new THREE.MeshLambertMaterial({ color: "#111e25" });
  private readonly rim = new THREE.MeshLambertMaterial({ color: "#a5b9bd" });
  private readonly accent = new THREE.MeshLambertMaterial({ color: "#e1edf0" });
  private readonly skins = new Map<string, THREE.MeshLambertMaterial>();

  constructor() {
    // Sloped windshield and rear glass, in normalized width/height/length coordinates.
    const vertices = [
      -.43,.54,-.27, .43,.54,-.27, .43,.54,.32, -.43,.54,.32,
      -.35,.92,-.10, .35,.92,-.10, .35,.92,.20, -.35,.92,.20,
    ];
    this.cabin = new THREE.BufferGeometry();
    this.cabin.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    this.cabin.setIndex([0,4,5,0,5,1, 1,5,6,1,6,2, 2,6,7,2,7,3, 3,7,4,3,4,0, 4,7,6,4,6,5, 0,1,2,0,2,3]);
    this.cabin.computeVertexNormals();
  }

  private skin(color: string) {
    if (!this.skins.has(color)) this.skins.set(color, new THREE.MeshLambertMaterial({ color }));
    return this.skins.get(color)!;
  }

  private part(root: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material,
    position: [number,number,number], scale: [number,number,number]) {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position); mesh.scale.set(...scale); root.add(mesh); return mesh;
  }

  create(detection: ViewerDetection, color: string): THREE.Group {
    const root = new THREE.Group();
    root.position.set(-detection.center.left, detection.center.up - detection.size.height / 2, -detection.center.forward);
    root.rotation.y = detection.yawRadians;
    const { width: w, height: h, length: l } = detection.size;
    const paint = this.skin(color), form = objectForm(detection.className);
    if (form === "vehicle") {
      this.part(root, this.box, paint, [0,h*.39,0], [w*.95,h*.34,l]);
      this.part(root, this.cabin, this.glass, [0,0,0], [w,h,l]);
      this.part(root, this.box, paint, [0,h*.93,l*.05], [w*.72,h*.07,l*.31]);
      const radius = Math.min(h*.19,l*.09);
      for (const x of [-1,1]) for (const z of [-1,1]) {
        const tyre = this.part(root, this.cylinder, this.tyre, [x*w*.43,radius,z*l*.30], [radius,w*.14,radius]); tyre.rotation.z = Math.PI/2;
        const rim = this.part(root, this.cylinder, this.rim, [x*w*.499,radius,z*l*.30], [radius*.55,.015,radius*.55]); rim.rotation.z = Math.PI/2;
      }
      for (const x of [-1,1]) {
        this.part(root, this.box, this.accent, [x*w*.31,h*.42,-l*.501], [w*.18,h*.10,.025]);
      }
    } else if (form === "person") {
      const headRadius = Math.min(h*.085,w*.26,l*.26);
      this.part(root, this.sphere, paint, [0,h-headRadius,0], [headRadius,headRadius,headRadius]);
      // Capsules have total height 3; all body parts stay within the predicted box.
      this.part(root, this.capsule, paint, [0,h*.64,0], [w*.23,h*.13,l*.21]);
      for (const side of [-1,1]) {
        const arm = this.part(root, this.capsule, paint, [side*w*.34,h*.61,0], [w*.09,h*.105,l*.10]); arm.rotation.z = side*.10;
        this.part(root, this.capsule, paint, [side*w*.16,h*.25,0], [w*.105,h*.14,l*.12]);
        this.part(root, this.box, this.tyre, [side*w*.16,h*.025,-l*.06], [w*.24,h*.05,l*.34]);
      }
    } else {
      this.part(root, this.box, paint, [0,h/2,0], [w,h,l]);
    }
    return root;
  }

  dispose() {
    [this.box,this.sphere,this.cylinder,this.capsule,this.cabin].forEach(g => g.dispose());
    [this.glass,this.tyre,this.rim,this.accent,...this.skins.values()].forEach(m => m.dispose());
  }
}
