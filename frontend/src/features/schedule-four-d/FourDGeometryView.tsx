import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import webIfcWasmUrl from "web-ifc/web-ifc.wasm?url";
import { scopeApi } from "../scope-foundation/api";
import { itemVisual } from "./visualStates";
import type { FourDItem } from "./types";

/** Transient render projection of immutable Scope IFC bytes. No geometry is persisted here. */
export default function FourDGeometryView({
  token,
  workspaceId,
  items,
  colors,
  onSelect,
}: {
  token: string;
  workspaceId: number;
  items: FourDItem[];
  colors: Record<string, unknown>;
  onSelect: (item: FourDItem) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const meshes = useRef<THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>[]>([]);
  const itemsRef = useRef(items);
  const colorsRef = useRef(colors);
  const selectionRef = useRef(onSelect);
  const [status, setStatus] = useState("Esperando referencias geométricas IFC…");
  const [error, setError] = useState("");
  useEffect(() => {
    itemsRef.current = items;
    colorsRef.current = colors;
    selectionRef.current = onSelect;
  }, [items, colors, onSelect]);
  const modelKey = useMemo(
    () =>
      [...new Set(items.flatMap((item) => item.objects.map((object) => object.model_version_id)))]
        .sort((a, b) => a - b)
        .join(","),
    [items]
  );
  useEffect(() => {
    for (const mesh of meshes.current) {
      const memberships = items.filter((item) =>
        item.objects.some(
          (object) =>
            object.model_version_id === mesh.userData.modelVersionId &&
            (object.express_id === mesh.userData.expressId || (object.guid && object.guid === mesh.userData.guid))
        )
      );
      const visible = memberships.filter((item) => itemVisual(item, colors).visible);
      mesh.visible = visible.length > 0;
      const state = visible.find((item) => item.visual_classes.includes("BLOCKED_BY_READINESS")) ?? visible[0];
      if (state) {
        const visual = itemVisual(state, colors);
        mesh.material.color.set(visual.color);
        mesh.material.opacity = visual.opacity;
        mesh.material.transparent = visual.opacity < 1;
        mesh.material.depthWrite = visual.opacity >= 1;
      }
    }
    const canvas = host.current?.querySelector("canvas");
    if (canvas) canvas.dataset.visibleMeshCount = String(meshes.current.filter((mesh) => mesh.visible).length);
  }, [items, colors]);
  useEffect(() => {
    const container = host.current;
    if (!container || !modelKey) return;
    let disposed = false;
    let frame = 0;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch (caught) {
      queueMicrotask(() => {
        if (!disposed) setError(`WebGL no disponible: ${String(caught)}`);
      });
      return;
    }
    queueMicrotask(() => {
      if (!disposed) setError("");
    });
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#edf2f5");
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000000);
    // web-ifc's render geometry uses Y-up, as does the existing IFC viewer.
    camera.up.set(0, 1, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.setAttribute("aria-label", "4D immutable IFC geometry canvas");
    container.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight("#ffffff", "#647b8a", 2.2));
    const light = new THREE.DirectionalLight("#ffffff", 3);
    light.position.set(20, -10, 30);
    scene.add(light);
    const group = new THREE.Group();
    scene.add(group);
    const localMeshes: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>[] = [];
    meshes.current = localMeshes;
    const resize = () => {
      const width = Math.max(container.clientWidth, 200);
      const height = 420;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    const pick = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1
      );
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(
        localMeshes.filter((mesh) => mesh.visible),
        false
      )[0]?.object;
      if (!hit) return;
      const item = itemsRef.current.find(
        (row) =>
          row.visible &&
          row.objects.some(
            (object) =>
              object.model_version_id === hit.userData.modelVersionId &&
              (object.express_id === hit.userData.expressId || (object.guid && object.guid === hit.userData.guid))
          )
      );
      if (item) selectionRef.current(item);
    };
    renderer.domElement.addEventListener("click", pick);
    const draw = () => {
      if (disposed) return;
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    draw();
    async function load() {
      setStatus("Cargando geometría real desde IFC canónico…");
      let omitted = 0;
      let triangles = 0;
      const { IfcAPI } = await import("web-ifc");
      for (const modelId of modelKey.split(",").map(Number)) {
        if (disposed) return;
        const bytes = new Uint8Array(await (await scopeApi.source(token, workspaceId, modelId)).arrayBuffer());
        if (disposed) return;
        const api = new IfcAPI();
        let opened: number | null = null;
        try {
          await api.Init((path) => (path.endsWith(".wasm") ? webIfcWasmUrl : path), true);
          if (disposed) return;
          opened = api.OpenModel(bytes);
          const flatMeshes = api.LoadAllGeometry(opened);
          try {
            for (let index = 0; index < flatMeshes.size(); index += 1) {
              const flat = flatMeshes.get(index);
              const memberships = itemsRef.current.filter((item) =>
                item.objects.some(
                  (object) => object.model_version_id === modelId && object.express_id === flat.expressID
                )
              );
              const object = memberships
                .flatMap((item) => item.objects)
                .find((row) => row.model_version_id === modelId && row.express_id === flat.expressID);
              for (let placedIndex = 0; placedIndex < flat.geometries.size(); placedIndex += 1) {
                const placed = flat.geometries.get(placedIndex);
                const geometry = api.GetGeometry(opened, placed.geometryExpressID);
                try {
                  const vertices = api.GetVertexArray(geometry.GetVertexData(), geometry.GetVertexDataSize());
                  const indices = api.GetIndexArray(geometry.GetIndexData(), geometry.GetIndexDataSize());
                  if (
                    !vertices.length ||
                    !indices.length ||
                    localMeshes.length >= 12000 ||
                    triangles + indices.length / 3 > 1500000
                  ) {
                    omitted += 1;
                    continue;
                  }
                  const positions = new Float32Array(vertices.length / 2);
                  const normals = new Float32Array(vertices.length / 2);
                  for (let v = 0; v < vertices.length; v += 6) {
                    const offset = v / 2;
                    positions.set(vertices.subarray(v, v + 3), offset);
                    normals.set(vertices.subarray(v + 3, v + 6), offset);
                  }
                  const buffer = new THREE.BufferGeometry();
                  buffer.setAttribute("position", new THREE.BufferAttribute(positions, 3));
                  buffer.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
                  buffer.setIndex(new THREE.BufferAttribute(indices.slice(), 1));
                  buffer.applyMatrix4(new THREE.Matrix4().fromArray(placed.flatTransformation));
                  const member =
                    memberships.find((item) => item.visible && item.visual_classes.includes("BLOCKED_BY_READINESS")) ??
                    memberships.find((item) => item.visible) ??
                    memberships[0];
                  const visual = member ? itemVisual(member, colorsRef.current) : { color: "#697582", opacity: 1 };
                  const mesh = new THREE.Mesh(
                    buffer,
                    new THREE.MeshStandardMaterial({
                      color: visual.color,
                      roughness: 0.8,
                      metalness: 0.05,
                      side: THREE.DoubleSide,
                      opacity: visual.opacity,
                      transparent: visual.opacity < 1,
                      depthWrite: visual.opacity >= 1,
                    })
                  );
                  mesh.userData = { modelVersionId: modelId, expressId: flat.expressID, guid: object?.guid };
                  mesh.visible = memberships.some((item) => item.visible);
                  localMeshes.push(mesh);
                  group.add(mesh);
                  triangles += indices.length / 3;
                } catch {
                  omitted += 1;
                } finally {
                  geometry.delete();
                }
              }
              if ("delete" in flat && typeof flat.delete === "function") flat.delete();
            }
          } finally {
            if ("delete" in flatMeshes && typeof flatMeshes.delete === "function") flatMeshes.delete();
          }
        } finally {
          if (opened !== null) api.CloseModel(opened);
          api.Dispose();
        }
      }
      if (disposed) return;
      renderer.domElement.dataset.meshCount = String(localMeshes.length);
      renderer.domElement.dataset.visibleMeshCount = String(localMeshes.filter((mesh) => mesh.visible).length);
      renderer.domElement.dataset.triangleCount = String(Math.round(triangles));
      const box = new THREE.Box3();
      localMeshes.forEach((mesh) => box.expandByObject(mesh));
      if (!box.isEmpty()) {
        const center = box.getCenter(new THREE.Vector3());
        const radius = Math.max(box.getSize(new THREE.Vector3()).length(), 0.1);
        camera.position.copy(center).add(new THREE.Vector3(radius, radius * 0.8, radius));
        camera.near = Math.max(radius / 10000, 0.001);
        camera.far = radius * 100;
        camera.updateProjectionMatrix();
        controls.target.copy(center);
        controls.update();
      }
      setStatus(
        `${localMeshes.length} mallas IFC reales · ${Math.round(triangles)} triángulos · ${omitted} geometrías omitidas${localMeshes.length ? "" : " · Sin geometría disponible para los vínculos seleccionados"}`
      );
    }
    void load().catch((caught) => {
      if (!disposed) setError(`No se pudo representar el IFC original: ${String(caught)}`);
    });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener("click", pick);
      controls.dispose();
      localMeshes.forEach((mesh) => {
        mesh.geometry.dispose();
        mesh.material.dispose();
      });
      meshes.current = [];
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [modelKey, token, workspaceId]);
  return (
    <section className="fourDGeometry" aria-label="4D geometry projection">
      <p role="status">
        {modelKey ? status : "Sin referencias IFC. No se fabrica geometría para Scope manual o Excel."}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      <div ref={host} className="fourDCanvas" />
    </section>
  );
}
