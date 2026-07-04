(function () {
  "use strict";

  var heroState = null;

  function disposeHero() {
    if (!heroState) return;
    cancelAnimationFrame(heroState.rafId);
    window.removeEventListener("resize", heroState.onResize);
    if (heroState.resizeObserver) heroState.resizeObserver.disconnect();
    heroState.renderer.dispose();
    if (heroState.renderer.domElement.parentNode) {
      heroState.renderer.domElement.parentNode.removeChild(heroState.renderer.domElement);
    }
    heroState = null;
  }

  function initHero() {
    disposeHero();

    var container = document.getElementById("glyphviz-hero-canvas");
    if (!container || typeof THREE === "undefined") return;

    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var palette = {
      torus: 0x534ab7,
      torusLight: 0x7f77dd,
      sphere: 0x0f6e56,
      sphereLight: 0x5dcaa5,
      grandchild: 0x1d9e75,
      cylinder: 0x7f77dd,
      cone: 0xd85a30,
      coneLight: 0xf0997b,
      edge: 0x9c96e0
    };

    var width = container.clientWidth;
    var height = container.clientHeight || 460;

    var scene = new THREE.Scene();

    var camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
    camera.position.set(0, 2.4, 11);

    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    var controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.autoRotate = !reduceMotion;
    controls.autoRotateSpeed = 0.6;
    controls.minPolarAngle = Math.PI * 0.28;
    controls.maxPolarAngle = Math.PI * 0.72;

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    var key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(5, 6, 7);
    scene.add(key);
    var rim = new THREE.DirectionalLight(0x9c96e0, 0.35);
    rim.position.set(-6, -3, -4);
    scene.add(rim);

    var root = new THREE.Group();
    scene.add(root);

    // Parent: torus
    var torus = new THREE.Mesh(
      new THREE.TorusGeometry(1.7, 0.55, 24, 64),
      new THREE.MeshStandardMaterial({ color: palette.torus, roughness: 0.45, metalness: 0.12 })
    );
    torus.rotation.x = Math.PI / 2.4;
    root.add(torus);

    // Orbit pivots for children (each pivot rotates independently -> orbit motion)
    function makePivot(tiltX, tiltZ) {
      var p = new THREE.Group();
      p.rotation.x = tiltX;
      p.rotation.z = tiltZ;
      root.add(p);
      return p;
    }

    var spherePivot = makePivot(0.15, 0.05);
    var sphereOrbitR = 3.6;
    var sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.62, 32, 32),
      new THREE.MeshStandardMaterial({ color: palette.sphere, roughness: 0.35, metalness: 0.08 })
    );
    sphere.position.set(sphereOrbitR, 0, 0);
    spherePivot.add(sphere);

    // Grandchild orbiting the sphere itself
    var grandchildPivot = new THREE.Group();
    sphere.add(grandchildPivot);
    var grandchild = new THREE.Mesh(
      new THREE.SphereGeometry(0.24, 20, 20),
      new THREE.MeshStandardMaterial({ color: palette.grandchild, roughness: 0.35, metalness: 0.08 })
    );
    grandchild.position.set(1.15, 0.25, 0);
    grandchildPivot.add(grandchild);

    var cylinderPivot = makePivot(-0.22, 0.35);
    var cylinderOrbitR = 3.1;
    var cylinder = new THREE.Mesh(
      new THREE.CylinderGeometry(0.5, 0.5, 1.0, 28),
      new THREE.MeshStandardMaterial({ color: palette.cylinder, roughness: 0.4, metalness: 0.1 })
    );
    cylinder.position.set(-cylinderOrbitR * 0.6, 0, cylinderOrbitR * 0.8);
    cylinderPivot.add(cylinder);

    var conePivot = makePivot(0.3, -0.4);
    var coneOrbitR = 3.9;
    var cone = new THREE.Mesh(
      new THREE.ConeGeometry(0.62, 1.3, 32),
      new THREE.MeshStandardMaterial({ color: palette.cone, roughness: 0.4, metalness: 0.08 })
    );
    cone.position.set(-coneOrbitR * 0.7, 0, -coneOrbitR * 0.7);
    conePivot.add(cone);

    // Hierarchy edges: thin lines redrawn each frame from torus center to each child's world position
    var edgeMat = new THREE.LineBasicMaterial({ color: palette.edge, transparent: true, opacity: 0.45 });
    function makeEdge() {
      var geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
      var line = new THREE.Line(geo, edgeMat);
      scene.add(line);
      return line;
    }
    var edgeToSphere = makeEdge();
    var edgeToCylinder = makeEdge();
    var edgeToCone = makeEdge();
    var edgeToGrandchild = makeEdge();

    var origin = new THREE.Vector3();
    var tmpA = new THREE.Vector3();
    var tmpB = new THREE.Vector3();

    function updateEdge(line, fromObj, toObj) {
      fromObj.getWorldPosition(tmpA);
      toObj.getWorldPosition(tmpB);
      var pos = line.geometry.attributes.position;
      pos.setXYZ(0, tmpA.x, tmpA.y, tmpA.z);
      pos.setXYZ(1, tmpB.x, tmpB.y, tmpB.z);
      pos.needsUpdate = true;
    }

    var spherePivotSpeed = 0.09;
    var cylinderPivotSpeed = -0.13;
    var conePivotSpeed = 0.07;
    var grandchildSpeed = 0.55;

    function onResize() {
      var w = container.clientWidth;
      var h = container.clientHeight || 460;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", onResize);

    var resizeObserver = null;
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(container);
    }

    var clock = new THREE.Clock();

    function animate() {
      heroState.rafId = requestAnimationFrame(animate);
      var dt = reduceMotion ? 0 : clock.getDelta();

      spherePivot.rotation.y += spherePivotSpeed * dt;
      cylinderPivot.rotation.y += cylinderPivotSpeed * dt;
      conePivot.rotation.y += conePivotSpeed * dt;
      grandchildPivot.rotation.y += grandchildSpeed * dt;
      torus.rotation.z += 0.05 * dt;

      updateEdge(edgeToSphere, torus, sphere);
      updateEdge(edgeToCylinder, torus, cylinder);
      updateEdge(edgeToCone, torus, cone);
      updateEdge(edgeToGrandchild, sphere, grandchild);

      controls.update();
      renderer.render(scene, camera);
    }

    heroState = {
      renderer: renderer,
      onResize: onResize,
      resizeObserver: resizeObserver,
      rafId: 0
    };
    animate();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(function () {
      initHero();
    });
  } else {
    document.addEventListener("DOMContentLoaded", initHero);
  }
})();
