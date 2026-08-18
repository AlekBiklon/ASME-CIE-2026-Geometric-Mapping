def my_cad_function(args):
    import cadquery as cq
    import os

    # --------- Resolve STEP path ---------
    step_path = None
    if isinstance(args, dict):
        step_path = args.get("input_file")
        if step_path:
            step_path = os.path.expanduser(step_path)

    fallback_paths = [
        r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/F332D3FXML85WLR2_1769686191.840884.step",
        r"C:\\PROGRAMING_PYTHON\\2026-08-14_ASME_Hackathon_2026\\neuralCAD-Edit-data\\edit_192_external\\breps\\F332D3FXML85WLR2_1769686191.840884.step",
    ]

    if not step_path or not os.path.exists(step_path):
        for p in fallback_paths:
            if os.path.exists(p):
                step_path = p
                break

    if not step_path or not os.path.exists(step_path):
        # last resort: search current dir and output_dir for a step
        roots = [os.getcwd()]
        if isinstance(args, dict) and args.get("output_dir"):
            roots.insert(0, os.path.expanduser(args["output_dir"]))
        found = []
        for r in roots:
            try:
                for fn in os.listdir(r):
                    if fn.lower().endswith((".step", ".stp")):
                        found.append(os.path.join(r, fn))
            except Exception:
                pass
        if found:
            step_path = sorted(found)[-1]

    if not step_path or not os.path.exists(step_path):
        raise ValueError("Could not resolve STEP input path")

    print(f"Loading STEP: {step_path}")
    imported = cq.importers.importStep(step_path)

    # Pick largest solid
    try:
        solids = imported.solids().vals()
        solid = max(solids, key=lambda s: s.Volume())
    except Exception:
        solid = imported.val() if hasattr(imported, "val") else imported

    bbox = solid.BoundingBox()
    dims = {"X": float(bbox.xlen), "Y": float(bbox.ylen), "Z": float(bbox.zlen)}
    thickness_axis = min(dims, key=dims.get)
    thickness = float(dims[thickness_axis])

    # --------- OCP helpers to read circle data robustly ---------
    def edge_circle_data(edge):
        """Return (center Vector, radius float, normal/axis Vector) for circular edges, else None."""
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GeomAbs import GeomAbs_Circle
            ad = BRepAdaptor_Curve(edge.wrapped)
            if ad.GetType() != GeomAbs_Circle:
                return None
            circ = ad.Circle()
            loc = circ.Location()
            ax = circ.Axis()
            d = ax.Direction()
            c = cq.Vector(loc.X(), loc.Y(), loc.Z())
            n = cq.Vector(d.X(), d.Y(), d.Z())
            r = float(circ.Radius())
            return c, r, n
        except Exception:
            return None

    def unit(v: cq.Vector):
        L = v.Length
        if L < 1e-9:
            return cq.Vector(0, 0, 1)
        return cq.Vector(v.x / L, v.y / L, v.z / L)

    def dist_point_to_line(pt: cq.Vector, p0: cq.Vector, d: cq.Vector):
        # distance = |(pt-p0) x d_unit|
        du = unit(d)
        return (pt.sub(p0)).cross(du).Length

    # --------- Find the face containing the two counterbore openings ---------
    planar_faces = [f for f in solid.Faces() if f.geomType() == "PLANE"]

    def face_circle_edges(face):
        ces = []
        for e in face.Edges():
            if e.geomType() == "CIRCLE":
                ced = edge_circle_data(e)
                if ced is not None:
                    ces.append((e, ced))
        return ces

    best_face = None
    best_score = (-1, -1.0)
    best_face_circles = None
    for f in planar_faces:
        ces = face_circle_edges(f)
        score = (len(ces), float(f.Area()))
        if score > best_score:
            best_score = score
            best_face = f
            best_face_circles = ces

    if best_face is None or not best_face_circles or len(best_face_circles) < 2:
        raise ValueError("Could not find a planar face with the existing hole openings")

    # Cluster openings by center (two holes)
    clusters = []  # {center:Vector, radii:[...], normals:[...]}
    for _, (c, r, n) in best_face_circles:
        placed = False
        for cl in clusters:
            if c.sub(cl["center"]).Length < 0.1:
                cl["radii"].append(r)
                cl["normals"].append(n)
                placed = True
                break
        if not placed:
            clusters.append({"center": c, "radii": [r], "normals": [n]})

    if len(clusters) < 2:
        raise ValueError("Expected two hole openings on the selected face")

    # Choose two clusters farthest apart (the two holes)
    best_pair = (0, 1)
    best_d = -1.0
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            d = clusters[i]["center"].sub(clusters[j]["center"]).Length
            if d > best_d:
                best_d = d
                best_pair = (i, j)

    h1 = clusters[best_pair[0]]["center"]
    h2 = clusters[best_pair[1]]["center"]
    mid = cq.Vector((h1.x + h2.x) / 2.0, (h1.y + h2.y) / 2.0, (h1.z + h2.z) / 2.0)

    # Counterbore opening radius is what we see on this face
    cbore_r = float(max(clusters[best_pair[0]]["radii"]))

    # Hole direction normal from the circle edge(s)
    hole_dir = unit(sum(clusters[best_pair[0]]["normals"], cq.Vector(0, 0, 0)))

    # --------- Analyze cylindrical faces to recover thru-hole radius and counterbore depth ---------
    cyl_faces = [f for f in solid.Faces() if f.geomType() == "CYLINDER"]

    cyl_infos = []  # dict: p0, dir, radius, length
    for f in cyl_faces:
        cedges = []
        for e in f.Edges():
            if e.geomType() == "CIRCLE":
                ced = edge_circle_data(e)
                if ced is not None:
                    cedges.append(ced)
        if len(cedges) < 2:
            continue

        # Prefer circles whose normals align (end circles)
        # Use first circle's normal as axis direction.
        d0 = unit(cedges[0][2])
        # Find min/max along d0 using centers
        ts = [(cedges[k][0].dot(d0), cedges[k][0]) for k in range(len(cedges))]
        tmin, pmin = min(ts, key=lambda x: x[0])
        tmax, pmax = max(ts, key=lambda x: x[0])
        length = abs(tmax - tmin)

        # radius: take median of edge radii (robust)
        rs = sorted([float(x[1]) for x in cedges])
        radius = rs[len(rs) // 2]

        cyl_infos.append({"p0": pmin, "dir": d0, "radius": radius, "length": float(length)})

    def pick_hole_parameters(hole_center: cq.Vector):
        # associate cylinders whose axis passes through hole_center and is parallel to hole_dir
        assoc = []
        for ci in cyl_infos:
            if abs(unit(ci["dir"]).dot(hole_dir)) < 0.95:
                continue
            d = dist_point_to_line(hole_center, ci["p0"], ci["dir"])
            if d < 0.2:  # mm
                assoc.append(ci)

        if len(assoc) < 2:
            return None

        assoc_sorted = sorted(assoc, key=lambda x: x["radius"])
        thru = assoc_sorted[0]
        cb = assoc_sorted[-1]

        # Counterbore depth should be the short larger-radius cylinder
        cbore_depth = float(cb["length"])
        thru_r = float(thru["radius"])

        # sanity corrections
        if cbore_depth <= 0 or cbore_depth >= thickness:
            # fall back: choose the shortest assoc length as counterbore depth
            cbore_depth = float(min(a["length"] for a in assoc if a["length"] > 0.01))
        return thru_r, float(cb["radius"]), cbore_depth

    params = pick_hole_parameters(h1)
    if params is None:
        # fallback: estimate thru radius from the smallest cylinder radius, and cbore depth as thickness/4
        print("WARNING: could not robustly associate cylinders to hole axis; using fallback parameters")
        if cyl_infos:
            thru_r = float(min(ci["radius"] for ci in cyl_infos))
        else:
            thru_r = cbore_r * 0.6
        cbore_depth = max(thickness / 4.0, 0.5)
    else:
        thru_r, cb_r_found, cbore_depth = params
        # keep cbore radius from opening face (most reliable for the top opening)
        # (cb_r_found should be close to cbore_r)
        if abs(cb_r_found - cbore_r) > max(0.2, 0.05 * cbore_r):
            print(f"Note: cbore radius from cylinders ({cb_r_found:.4f}) differs from opening ({cbore_r:.4f}); using opening")

    print(f"Thickness axis: {thickness_axis}, thickness={thickness:.4f}")
    print(f"Existing holes: h1=({h1.x:.4f},{h1.y:.4f},{h1.z:.4f}), h2=({h2.x:.4f},{h2.y:.4f},{h2.z:.4f})")
    print(f"New hole mid:   ({mid.x:.4f},{mid.y:.4f},{mid.z:.4f})")
    print(f"Using: thru_d={2*thru_r:.4f}, cbore_d={2*cbore_r:.4f}, cbore_depth={cbore_depth:.4f}, depth={thickness + 0.5:.4f}")

    # --------- Cut new counterbored through-hole on the same face ---------
    base = cq.Workplane(obj=solid)
    face_sel = cq.selectors.NearestToPointSelector(best_face.Center())

    wp = base.faces(face_sel).workplane(centerOption="CenterOfMass")
    mid_local = wp.plane.toLocalCoords(mid)

    result = (
        base
        .faces(face_sel)
        .workplane(centerOption="CenterOfMass")
        .pushPoints([(mid_local.x, mid_local.y)])
        .cboreHole(2.0 * thru_r, 2.0 * cbore_r, cbore_depth, depth=thickness + 0.5)
    )

    return result
