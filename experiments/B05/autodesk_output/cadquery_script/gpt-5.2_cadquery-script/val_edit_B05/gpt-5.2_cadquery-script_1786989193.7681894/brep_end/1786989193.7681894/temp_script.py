def my_cad_function(args):
    import os
    import cadquery as cq

    # Task-provided STEP path (runner may not pass input_file)
    preferred_step = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/4S7JQK6ZQMAD25GL_1758863189.5437753.step"

    def _norm(p):
        return os.path.normpath(os.path.expanduser(str(p)))

    def _find_step_path(a):
        for k in ["input_file", "brep_start_path_step", "brep_start_path", "step_path", "model_path"]:
            p = a.get(k)
            if p and str(p).lower().endswith(".step") and os.path.exists(_norm(p)):
                return _norm(p)
        if os.path.exists(_norm(preferred_step)):
            return _norm(preferred_step)
        # last resort: look in same dir for tagged step
        tag = "4S7JQK6ZQMAD25GL"
        d = os.path.dirname(_norm(preferred_step))
        if os.path.isdir(d):
            cands = [
                os.path.join(d, fn)
                for fn in os.listdir(d)
                if fn.lower().endswith(".step")
                and fn.lower() != "tmp.step"
                and tag.lower() in fn.lower()
            ]
            if cands:
                return max(cands, key=lambda p: os.path.getmtime(p))
        return None

    step_path = _find_step_path(args)
    if not step_path or not os.path.exists(step_path):
        print("Args keys:", sorted(list(args.keys())))
        raise ValueError("Could not locate STEP for edit task")

    print("Loading STEP:", step_path)
    model = cq.importers.importStep(step_path)
    base = model.val() if hasattr(model, "val") else model

    solids = list(base.Solids())
    if not solids:
        solids = [base]

    fillet_r = 2.0

    def _wire_perimeter(w):
        try:
            return sum(e.Length() for e in w.Edges())
        except Exception:
            try:
                return w.Length()
            except Exception:
                return 0.0

    def _safe_len(ed):
        try:
            return ed.Length()
        except Exception:
            return 1e9

    def _try_fillet_edges_on_solid(solid, edges, label=""):
        """Try batch then sequential per-edge fillet. Return modified solid or None."""
        edges = list(edges) if edges else []
        if not edges:
            return None

        # Batch
        try:
            out = solid.fillet(fillet_r, edges)
            print(f"{label}: fillet succeeded (batch) on {len(edges)} edges")
            return out
        except Exception as e:
            # Sequential per-edge
            curr = solid
            applied = 0
            edges2 = sorted(edges, key=_safe_len)
            for ed in edges2:
                try:
                    curr = curr.fillet(fillet_r, [ed])
                    applied += 1
                except Exception:
                    continue
            if applied > 0:
                print(f"{label}: fillet succeeded (sequential) applied {applied}/{len(edges2)}")
                return curr
            print(f"{label}: fillet failed (batch+sequential): {e}")
            return None

    def _face_plane_axes(face):
        """Return (origin, xAxis, yAxis, zAxis) for approximate face plane."""
        origin = face.Center()
        # normal
        try:
            zAxis = face.normalAt(origin)
        except Exception:
            try:
                zAxis = face.normalAt()
            except Exception:
                zAxis = cq.Vector(0, 0, 1)
        try:
            zAxis = zAxis.normalized()
        except Exception:
            zAxis = cq.Vector(0, 0, 1)

        ref = cq.Vector(0, 0, 1)
        try:
            if abs(zAxis.dot(ref)) > 0.95:
                ref = cq.Vector(1, 0, 0)
        except Exception:
            ref = cq.Vector(1, 0, 0)

        xAxis = zAxis.cross(ref)
        try:
            xAxis = xAxis.normalized()
        except Exception:
            xAxis = cq.Vector(1, 0, 0)

        yAxis = zAxis.cross(xAxis)
        try:
            yAxis = yAxis.normalized()
        except Exception:
            yAxis = cq.Vector(0, 1, 0)

        return origin, xAxis, yAxis, zAxis

    def _wire_bbox_in_face_plane(face, wire):
        """Compute approximate 2D bbox (dx, dy) of wire vertices in the face plane basis."""
        o, xA, yA, _ = _face_plane_axes(face)
        try:
            verts = list(wire.Vertices())
        except Exception:
            verts = []
        if not verts:
            try:
                verts = []
                for ed in wire.Edges():
                    verts.extend(list(ed.Vertices()))
            except Exception:
                verts = []
        if not verts:
            return None

        xs, ys = [], []
        for v in verts:
            try:
                p = v.Center()
            except Exception:
                continue
            try:
                d = p.sub(o)
                xs.append(d.dot(xA))
                ys.append(d.dot(yA))
            except Exception:
                continue

        if not xs or not ys:
            return None
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        return abs(dx), abs(dy)

    def _find_best_scroll_slot_wire(solid):
        """Pick an inner wire most likely to be the scroll-wheel slot opening."""
        sbb = solid.BoundingBox()
        faces = list(solid.Faces())

        best = None  # (score, face, wire, dx, dy, area_box, aspect, z_norm)

        for f in faces:
            try:
                wires = list(f.Wires())
            except Exception:
                continue
            if len(wires) < 2:
                continue

            perims = [(_wire_perimeter(w), w) for w in wires]
            perims.sort(key=lambda t: t[0], reverse=True)
            inner_wires = [w for _, w in perims[1:]]

            for w in inner_wires:
                bb2 = _wire_bbox_in_face_plane(f, w)
                if bb2 is None:
                    continue
                dx, dy = bb2
                mn = min(dx, dy)
                mx = max(dx, dy)
                if mn < 0.6:
                    continue

                area_box = dx * dy
                aspect = mx / max(mn, 1e-6)

                # Mild filters: avoid tiny holes; prefer somewhat elongated
                if area_box < 60.0:
                    continue
                if aspect < 1.15:
                    continue

                try:
                    wbb3 = w.BoundingBox()
                    z_norm = (wbb3.center.z - sbb.zmin) / max(sbb.zlen, 1e-6)
                except Exception:
                    z_norm = 0.5

                top_bonus = 1.0 + 1.2 * max(0.0, z_norm - 0.55)
                elong_bonus = 1.0 + 0.6 * min(6.0, max(0.0, aspect - 1.3))

                score = area_box * top_bonus * elong_bonus

                if best is None or score > best[0]:
                    best = (score, f, w, dx, dy, area_box, aspect, z_norm)

        return best

    def _heuristic_candidate_edges(solid):
        """Fallback if no inner-wire hole is found: select internal edges near top/mid."""
        bb = solid.BoundingBox()
        cx, cy = bb.center.x, bb.center.y
        z_top = bb.zmax

        z_min = z_top - max(3.0, 0.45 * bb.zlen)
        xw = 0.40 * bb.xlen
        yw = 0.40 * bb.ylen
        margin = max(3.0, 0.06 * min(bb.xlen, bb.ylen))
        max_len = max(40.0, 0.60 * min(bb.xlen, bb.ylen))
        min_len = 2.0

        def _is_candidate(e):
            c = e.Center()
            if c.z < z_min or c.z > z_top + 0.5:
                return False
            if abs(c.x - cx) > xw or abs(c.y - cy) > yw:
                return False
            if (c.x - bb.xmin) < margin or (bb.xmax - c.x) < margin:
                return False
            if (c.y - bb.ymin) < margin or (bb.ymax - c.y) < margin:
                return False
            try:
                L = e.Length()
                if L < min_len or L > max_len:
                    return False
            except Exception:
                pass
            return True

        wp = cq.Workplane("XY").newObject([solid])
        return list(wp.edges().filter(_is_candidate).vals())

    successes = []  # (score, solid_index, modified_solid)

    for i, s in enumerate(solids):
        try:
            sbb = s.BoundingBox()
            print(f"Solid {i}: bbox xlen={sbb.xlen:.3f} ylen={sbb.ylen:.3f} zlen={sbb.zlen:.3f}")
        except Exception:
            print(f"Solid {i}: bbox <error>")

        best = _find_best_scroll_slot_wire(s)
        if best is not None:
            score, face, wire, dx, dy, area_box, aspect, z_norm = best
            try:
                wbb3 = wire.BoundingBox()
                wc = wbb3.center
                ecount = len(list(wire.Edges()))
                print(
                    f"Solid {i}: slot-wire score={score:.2f} dx={dx:.3f} dy={dy:.3f} area={area_box:.1f} aspect={aspect:.2f} z_norm={z_norm:.2f} "
                    f"center=({wc.x:.3f},{wc.y:.3f},{wc.z:.3f}) edges={ecount}"
                )
            except Exception:
                print(f"Solid {i}: slot-wire score={score:.2f} (details <error>)")

            try:
                wire_edges = list(wire.Edges())
            except Exception:
                wire_edges = []

            mod = _try_fillet_edges_on_solid(s, wire_edges, label=f"Solid {i} slot-wire")
            if mod is not None:
                successes.append((score, i, mod))
                continue

        heur_edges = _heuristic_candidate_edges(s)
        print(f"Solid {i}: heuristic candidate edges={len(heur_edges)}")
        if heur_edges:
            mod2 = _try_fillet_edges_on_solid(s, heur_edges, label=f"Solid {i} heuristic")
            if mod2 is not None:
                successes.append((1.0, i, mod2))

    if not successes:
        print("No fillet applied; returning original model.")
        return model

    best_score, best_i, best_mod = max(successes, key=lambda t: t[0])
    print(f"Using modified solid index {best_i} (score={best_score:.2f})")

    solids_out = list(solids)
    solids_out[best_i] = best_mod

    if len(solids_out) == 1:
        return cq.Workplane("XY").newObject([solids_out[0]])

    try:
        comp = cq.Compound.makeCompound(solids_out)
        return cq.Workplane("XY").newObject([comp])
    except Exception:
        return cq.Workplane("XY").newObject([best_mod])
