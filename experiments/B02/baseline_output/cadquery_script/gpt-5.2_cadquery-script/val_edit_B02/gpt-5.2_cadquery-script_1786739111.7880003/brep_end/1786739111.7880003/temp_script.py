def my_cad_function(args):
    import os
    import cadquery as cq

    radius = 0.2  # mm

    def _walk_step_files(base, max_depth=10, max_found=2000):
        found = []
        if not base or not os.path.isdir(base):
            return found
        base = os.path.abspath(base)
        for root, dirs, files in os.walk(base):
            rel = os.path.relpath(root, base)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth >= max_depth:
                dirs[:] = []
            for fn in files:
                lfn = fn.lower()
                if lfn.endswith((".step", ".stp")):
                    found.append(os.path.join(root, fn))
                    if len(found) >= max_found:
                        return found
        return found

    def _ascend_dirs(p, levels=12):
        out = []
        if not p:
            return out
        d = os.path.abspath(p)
        if os.path.isfile(d):
            d = os.path.dirname(d)
        for _ in range(levels):
            if d and d not in out:
                out.append(d)
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        return out

    def _find_data_root(start_dirs):
        # look for a folder named "neuralCAD-Edit-data" in ancestors
        for sd in start_dirs:
            for anc in _ascend_dirs(sd, levels=18):
                cand = os.path.join(anc, "neuralCAD-Edit-data")
                if os.path.isdir(cand):
                    return cand
        return None

    def find_step_path():
        # 1) explicit args
        for k in ("input_file", "brep_start_path_step", "brep_start_path", "step_path", "path"):
            p = args.get(k)
            if p:
                p = os.path.expanduser(str(p))
                if os.path.exists(p) and p.lower().endswith((".step", ".stp")):
                    return os.path.abspath(p)

        # 2) local/ancestor search near runner paths
        bases = []
        bases.extend(_ascend_dirs(args.get("function_file"), levels=10))
        bases.extend(_ascend_dirs(args.get("output_dir"), levels=10))
        bases.extend(_ascend_dirs(os.getcwd(), levels=6))

        candidates = []
        for b in bases:
            candidates.extend(_walk_step_files(b, max_depth=10))
            # also try common subfolders
            candidates.extend(_walk_step_files(os.path.join(b, "breps"), max_depth=10))
            candidates.extend(_walk_step_files(os.path.join(b, "brep_start"), max_depth=10))

        # 3) search in the dataset root if present
        data_root = _find_data_root(bases)
        if data_root:
            # search only in likely subtrees to limit cost
            candidates.extend(_walk_step_files(data_root, max_depth=6))

        # de-dup and filter
        uniq = []
        seen = set()
        for c in candidates:
            ac = os.path.abspath(c)
            if ac in seen:
                continue
            seen.add(ac)
            if os.path.exists(ac):
                uniq.append(ac)

        if not uniq:
            print("ERROR: No STEP input found.")
            print("Args keys:", sorted(list(args.keys())))
            print("function_file:", args.get("function_file"))
            print("output_dir:", args.get("output_dir"))
            print("cwd:", os.getcwd())
            raise ValueError("No STEP input available.")

        # Prefer non-output tmp.step if possible
        def score(p):
            fn = os.path.basename(p).lower()
            is_tmp = 1 if fn in ("tmp.step", "tmp.stp") else 0
            in_breps = 1 if ("breps" in p.lower()) else 0
            try:
                sz = os.path.getsize(p)
            except Exception:
                sz = 0
            try:
                mt = os.path.getmtime(p)
            except Exception:
                mt = 0
            # sort: not tmp, in breps, larger, newer
            return (-is_tmp, in_breps, sz, mt)

        uniq.sort(key=score, reverse=True)
        chosen = uniq[0]
        print("Chosen STEP:", chosen)
        if data_root:
            print("Detected data root:", data_root)
        print("STEP candidates found:", len(uniq))
        return chosen

    step_path = find_step_path()
    model = cq.importers.importStep(step_path)
    shape = model.val() if hasattr(model, "val") else model

    # basic debug
    try:
        bb = shape.BoundingBox()
        print(f"Loaded valid: {getattr(shape, 'isValid', lambda: 'n/a')()}")
        print(f"Faces: {len(shape.Faces())}  Edges: {len(shape.Edges())}")
        print(f"BBox: x=[{bb.xmin:.3f},{bb.xmax:.3f}] y=[{bb.ymin:.3f},{bb.ymax:.3f}] z=[{bb.zmin:.3f},{bb.zmax:.3f}]")
    except Exception as e:
        print("Debug failed:", e)

    # Try filleting broadly ("sharp edges" approximated as all edges) with robustness fallbacks
    wp = cq.Workplane(obj=shape)
    try:
        res = wp.edges().fillet(radius)
        print(f"Applied {radius}mm fillet to all edges (workplane selection).")
        return res
    except Exception as e:
        print("Workplane fillet failed:", e)

    # Per-solid fillet fallback with progressive tiny-edge filtering
    try:
        solids = list(shape.Solids())
    except Exception:
        solids = []

    if solids:
        filleted = []
        any_done = False
        for i, s in enumerate(solids):
            edges_all = list(s.Edges())
            done = False
            for min_len in (0.0, 0.3, 0.8, 1.5, 3.0):
                edges = [ed for ed in edges_all if ed.Length() > float(min_len)]
                if not edges:
                    continue
                try:
                    fs = s.fillet(radius, edges)
                    filleted.append(fs)
                    any_done = True
                    done = True
                    print(f"Solid {i}: fillet {radius}mm applied (min edge length > {min_len}mm).")
                    break
                except Exception:
                    continue
            if not done:
                filleted.append(s)
                print(f"Solid {i}: fillet failed; kept original.")

        if any_done:
            if len(filleted) == 1:
                return cq.Workplane(obj=filleted[0])
            return cq.Workplane(obj=cq.Compound.makeCompound(filleted))

    print("Returning original model (no fillet applied due to errors).")
    return model
