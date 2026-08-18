def my_cad_function(args):
    import os
    import cadquery as cq

    # OCC helpers (available in CadQuery builds that use OCP)
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
    except Exception:
        BRepAdaptor_Surface = None
        GeomAbs_Cylinder = None

    def _expand(p):
        return os.path.expanduser(p) if isinstance(p, str) else p

    def _to_cq_vector(v):
        """Convert various point/vec representations to cq.Vector."""
        if isinstance(v, cq.Vector):
            return v
        # cadquery BoundingBox.center can be a tuple in some builds
        if isinstance(v, (tuple, list)) and len(v) >= 3:
            return cq.Vector(float(v[0]), float(v[1]), float(v[2]))
        # OCP gp_Pnt / gp_Vec / gp_Dir like objects
        for attrs in [("X", "Y", "Z"), ("x", "y", "z")]:
            if all(hasattr(v, a) for a in attrs):
                try:
                    return cq.Vector(float(getattr(v, attrs[0])()), float(getattr(v, attrs[1])()), float(getattr(v, attrs[2])()))
                except Exception:
                    try:
                        return cq.Vector(float(getattr(v, attrs[0])), float(getattr(v, attrs[1])), float(getattr(v, attrs[2])))
                    except Exception:
                        pass
        raise TypeError(f"Cannot convert to cq.Vector: {type(v)}")

    def _dot(a, b):
        a = _to_cq_vector(a)
        b = _to_cq_vector(b)
        return a.x * b.x + a.y * b.y + a.z * b.z

    def _safe_center(shape_obj):
        try:
            return _to_cq_vector(shape_obj.Center())
        except Exception:
            # fallback: bbox center
            bb = shape_obj.BoundingBox()
            return _to_cq_vector(bb.center)

    def _safe_normal(face):
        # normal at face center
        try:
            pt = face.Center()
        except Exception:
            return cq.Vector(0, 0, 1)
        try:
            u, v = face.paramAt(pt)
            return _to_cq_vector(face.normalAt(u, v))
        except Exception:
            try:
                return _to_cq_vector(face.normalAt())
            except Exception:
                return cq.Vector(0, 0, 1)

    def _is_closed_circle_edge(e):
        try:
            if str(e.geomType()).upper() != "CIRCLE":
                return False
        except Exception:
            return False
        try:
            return bool(e.isClosed())
        except Exception:
            try:
                return bool(e.wrapped.Closed())
            except Exception:
                return False

    def _is_hole_cyl_face(face):
        """Return True if this cylindrical face is likely an internal hole wall.

        Uses cylinder axis to decide: for holes, outward normal points toward the axis
        (dot(normal, radial_vector) < 0). For external bosses, it points away.
        """
        if BRepAdaptor_Surface is None:
            return False
        try:
            if str(face.geomType()).upper() != "CYLINDER":
                return False
        except Exception:
            return False

        try:
            ad = BRepAdaptor_Surface(face.wrapped)
            if GeomAbs_Cylinder is None or ad.GetType() != GeomAbs_Cylinder:
                return False
            cyl = ad.Cylinder()
            ax = cyl.Axis()  # gp_Ax1
            loc = ax.Location()  # gp_Pnt
            direc = ax.Direction()  # gp_Dir

            p = _safe_center(face)
            n = _safe_normal(face)

            # project p onto axis
            locv = _to_cq_vector(loc)
            dv = _to_cq_vector(direc)
            v = p - locv
            t = _dot(v, dv)
            axis_pt = locv + dv.multiply(t)
            radial = p - axis_pt

            # if radial is tiny, can't classify
            if radial.Length < 1e-6:
                return False

            return _dot(n, radial) < 0
        except Exception:
            return False

    def _collect_hole_mouth_edges(solid):
        """Collect closed circular edges that bound internal cylindrical faces (holes)."""
        hole_cyl_faces = []
        try:
            faces = solid.Faces()
        except Exception:
            faces = []

        for f in faces:
            if _is_hole_cyl_face(f):
                hole_cyl_faces.append(f)

        edges = []
        seen = set()
        for f in hole_cyl_faces:
            for e in f.Edges():
                if not _is_closed_circle_edge(e):
                    continue
                k = id(getattr(e, "wrapped", e))
                if k in seen:
                    continue
                seen.add(k)
                edges.append(e)

        return hole_cyl_faces, edges

    def _apply_chamfer(solid, edges, size=0.2):
        if not edges:
            return solid
        try:
            wp = cq.Workplane(obj=solid).newObject(edges)
            wp = wp.chamfer(size)
            return wp.val()
        except Exception as e:
            print(f"Chamfer failed: {e}")
            return solid

    def _find_step_path():
        # Prefer the known task STEP path
        known = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/ZK22J6VYRKQ2RTFD_1758875194.249227.step"
        if os.path.exists(known):
            return known

        # If the runner passed it in args
        p = _expand((args or {}).get("input_file", ""))
        if p and os.path.exists(p) and p.lower().endswith((".step", ".stp")):
            return p

        # Search common breps folder
        breps_dir = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps"
        candidates = []
        if os.path.isdir(breps_dir):
            for nm in os.listdir(breps_dir):
                if nm.lower().endswith((".step", ".stp")):
                    fp = os.path.join(breps_dir, nm)
                    candidates.append(fp)
        if not candidates:
            return ""
        candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        print("STEP discovery fallback (newest first), top 5:")
        for fp in candidates[:5]:
            try:
                print(f"  {fp} (mtime={os.path.getmtime(fp)})")
            except Exception:
                print(f"  {fp}")
        return candidates[0]

    step_path = _find_step_path()
    if not step_path or not os.path.exists(step_path):
        print(f"ERROR: Could not locate STEP. args keys: {list((args or {}).keys())}")
        return None

    print(f"Loading STEP: {step_path}")
    model = cq.importers.importStep(step_path)

    # Extract solids
    try:
        solids = model.solids().vals()
    except Exception:
        solids = []

    if not solids:
        v = model.val() if hasattr(model, "val") else model
        try:
            solids = v.Solids()
        except Exception:
            solids = []

    if not solids:
        print("WARNING: No solids found; returning imported model as-is.")
        return model

    out_solids = []
    for i, s in enumerate(solids):
        print(f"Processing solid {i+1}/{len(solids)}")
        hole_faces, hole_edges = _collect_hole_mouth_edges(s)
        print(f"  Hole cylindrical faces detected: {len(hole_faces)}")
        print(f"  Hole mouth circular edges selected for 0.2mm chamfer: {len(hole_edges)}")

        # Fallback: if detection fails (no OCC), chamfer all closed circular edges
        if not hole_edges:
            all_edges = []
            seen = set()
            try:
                for e in s.Edges():
                    if _is_closed_circle_edge(e):
                        k = id(getattr(e, "wrapped", e))
                        if k not in seen:
                            seen.add(k)
                            all_edges.append(e)
            except Exception:
                pass
            print(f"  Fallback closed circular edges for chamfer: {len(all_edges)}")
            hole_edges = all_edges

        out_solids.append(_apply_chamfer(s, hole_edges, size=0.2))

    if len(out_solids) == 1:
        return out_solids[0]

    try:
        return cq.Compound.makeCompound(out_solids)
    except Exception:
        # last resort: union
        res = cq.Workplane(obj=out_solids[0])
        for ss in out_solids[1:]:
            try:
                res = res.union(cq.Workplane(obj=ss))
            except Exception:
                pass
        return res.val()
