def my_cad_function(args):
    import os
    import cadquery as cq

    # Resolve STEP path
    step_path = None
    if isinstance(args, dict):
        step_path = args.get("input_file")
        if step_path:
            step_path = os.path.expanduser(step_path)

    if (not step_path) or (not os.path.exists(step_path)):
        step_path = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/3YH2WFSRM22W7DKT_1770125393.3132772.step"

    if not os.path.exists(step_path):
        print(f"STEP file not found: {step_path}")
        return None

    model = cq.importers.importStep(step_path)
    solid = model.val() if hasattr(model, "val") else model

    # Debug info
    try:
        bb = solid.BoundingBox()
        c = bb.center
        print(f"Loaded STEP: {os.path.basename(step_path)}")
        print(f"Valid: {solid.isValid()}")
        print(f"Faces: {len(solid.Faces())}, Edges: {len(solid.Edges())}")
        print(
            f"BBox: x[{bb.xmin:.3f},{bb.xmax:.3f}] y[{bb.ymin:.3f},{bb.ymax:.3f}] z[{bb.zmin:.3f},{bb.zmax:.3f}] center=({c.x:.3f},{c.y:.3f},{c.z:.3f})"
        )
    except Exception as e:
        print(f"Debug bbox failed: {e}")

    def circle_radius(edge):
        """Return radius for circular edges; otherwise None."""
        try:
            if edge.geomType() != "CIRCLE":
                return None
        except Exception:
            return None

        # Try CadQuery helper first
        try:
            r = float(edge.radius())
            return r
        except Exception:
            pass

        # Fallback: OCC adaptor
        try:
            ad = edge._geomAdaptor()
            circ = ad.Circle()
            return float(circ.Radius())
        except Exception:
            return None

    edges_all = list(solid.Edges())

    # Gather circle radii to distinguish outer-perimeter arcs from hole-mouth circles
    radii = []
    for e in edges_all:
        r = circle_radius(e)
        if r is not None:
            radii.append(r)

    radii_sorted = sorted(radii)
    # Compute an automatic threshold by finding the largest gap in sorted radii
    thr = None
    if len(radii_sorted) >= 2:
        max_gap = -1.0
        split_i = None
        for i in range(len(radii_sorted) - 1):
            gap = radii_sorted[i + 1] - radii_sorted[i]
            if gap > max_gap:
                max_gap = gap
                split_i = i
        # If there is a meaningful gap, split there; else choose a conservative threshold
        if max_gap > 1e-3 and split_i is not None:
            thr = 0.5 * (radii_sorted[split_i] + radii_sorted[split_i + 1])
        else:
            thr = radii_sorted[-1] + 1.0  # effectively selects none
    elif len(radii_sorted) == 1:
        thr = radii_sorted[0] + 1.0
    else:
        thr = None

    # Print circle radii diagnostics
    if radii_sorted:
        # Round for readability
        uniq = sorted({round(r, 3) for r in radii_sorted})
        print(f"Circle edge radii (unique, mm): {uniq}")
        print(f"Auto radius threshold for 'large circles': {thr:.3f} mm")
    else:
        print("No circular edges detected.")

    type_counts = {}
    candidates = []
    for e in edges_all:
        try:
            gt = e.geomType()
        except Exception:
            gt = "UNKNOWN"
        type_counts[gt] = type_counts.get(gt, 0) + 1

        # Always include straight sharp edges
        if gt == "LINE":
            candidates.append(e)
            continue

        # Include large-radius circular edges (typically outer perimeters), exclude small hole-mouth circles
        if gt == "CIRCLE" and thr is not None:
            r = circle_radius(e)
            if r is not None and r > thr:
                candidates.append(e)
            continue

    print(f"Edge geomType counts: {type_counts}")
    print(f"Fillet candidate edges: {len(candidates)} / {len(edges_all)}")

    wp = cq.Workplane("XY").add(solid)

    try:
        return wp.newObject(candidates).fillet(5.0)
    except Exception as e:
        print(f"Fillet(5.0) failed on candidate set: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: try fillet only LINE edges
        try:
            line_edges = [ed for ed in edges_all if (getattr(ed, "geomType", lambda: "")() == "LINE")]
            print(f"Fallback: fillet only LINE edges: {len(line_edges)}")
            return wp.newObject(line_edges).fillet(5.0)
        except Exception as e2:
            print(f"Fallback fillet on LINE edges also failed: {e2}")
            traceback.print_exc()
            return wp
