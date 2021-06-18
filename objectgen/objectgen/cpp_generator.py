import io

from collections import defaultdict
from typing import List, IO, Any, Tuple, Dict
from pathlib import Path

from .object_def import Namespace, ObjectDefinition
from .generator import Generator, ns_to_path, LICENSE

class CPPGenerator(Generator):
    def header_for(self, ns: Namespace) -> Path:
        ns_path = ns_to_path(ns)
        assert self.config.cpp_include_root, "C++ include root must be set."
        path = Path(self.config.cpp_include_root.joinpath(ns_path)).resolve()
        path.parents[0].mkdir(parents=True, exist_ok=True)
        return path.with_suffix(".h")

    def source_for(self, ns: Namespace) -> Path:
        ns_path = ns_to_path(ns)
        assert self.config.cpp_source_root, "C++ source root must be set."
        path = Path(self.config.cpp_source_root.joinpath(ns_path)).resolve()
        path.parents[0].mkdir(parents=True, exist_ok=True)
        return path.with_suffix(".cc")

    def generate_gitignore(self, ns: Namespace) -> None:
        # TODO(@jroesch): unify with above code
        source_ns = ns_to_path(ns[1:])
        assert self.config.cpp_source_root, "C++ source root must be set."
        source_path = Path(self.config.cpp_source_root.joinpath(source_ns)).resolve()
        source_path.parents[0].mkdir(parents=True, exist_ok=True)
        source_path = source_path.parents[0]

        header_ns = ns_to_path(ns)
        assert self.config.cpp_include_root, "C++ include root must be set."
        header_path = Path(self.config.cpp_include_root.joinpath(header_ns)).resolve()
        header_path.parents[0].mkdir(parents=True, exist_ok=True)
        header_path = header_path.parents[0]

        header_ignore_path = header_path.joinpath(".gitignore")
        source_ignore_path = source_path.joinpath(".gitignore")

        with open(header_ignore_path, 'w') as header_ignore:
            with open(source_ignore_path, 'w') as source_ignore:
                for file_name in self.generated_files:
                    if file_name.suffix == ".h":
                        file_to_ignore = file_name.relative_to(header_path)
                        header_ignore.write(f"{file_to_ignore}\n")
                    elif file_name.suffix == ".cc":
                        file_to_ignore = file_name.relative_to(source_path)
                        source_ignore.write(f"{file_to_ignore}\n")

    def generate(self, definitions: List[ObjectDefinition]) -> None:
        by_ns: Dict[Tuple[str, ...], List[ObjectDefinition]] = defaultdict(list)

        # Group definitions by namespaces.
        for defn in definitions:
            defn_ns = self.qualified_path(defn)
            by_ns[tuple(defn_ns)].append(defn)

        # Generate each NS to a set of files.
        for ns_key in by_ns:
            header = io.StringIO("")
            source = io.StringIO("")

            ns = list(ns_key)
            self.generate_ns(header, source, ns, by_ns[ns_key])

            # Ensure directory exists.
            header_file = self.header_for(ns)
            # NB: We want to map root namespace of any C++ project to src/
            # directory, so we slice the namespace and only pass, all namespaces
            # after the root ns.
            source_file = self.source_for(ns[1:])
            print(f"HeaderFile: {header_file}")
            print(f"SourceFile: {source_file}")

            license_str =("\n").join([f"* {line}" for line in LICENSE.splitlines()])
            license_str = f"/{license_str}\n*/"

            with self.open_file(header_file) as file:
                file.seek(0)
                file.truncate()
                file.write(license_str)
                file.write(header.getvalue())

            with self.open_file(source_file) as file:
                file.seek(0)
                file.truncate()
                file.write(license_str)
                file.write("\n")
                file.write(source.getvalue())

            self.generate_gitignore(ns)


    def generate_ns(self, header_buf: IO[Any], source_buf: IO[Any], namespace: Namespace, defs: List[ObjectDefinition]) -> None:
        header_value = "_".join([ns.upper() for ns in namespace])
        header_value = f"TVM_{header_value}_H_"
        header_buf.write("\n")
        header_buf.write(f"#ifndef {header_value}\n")
        header_buf.write(f"#define {header_value}\n")

        includes = []
        seen = set()

        for defn in defs:
            for imp in defn.imports:
                if tuple(imp) not in seen:
                    header_path = "/".join(imp) + ".h"
                    includes += [f"<{header_path}>"]
                    seen.add(tuple(imp))

        header_include = self.header_for(namespace)
        assert self.config.cpp_include_root, "C++ include root must be set."
        header_include = header_include.relative_to(self.config.cpp_include_root.resolve())
        source_includes = [f"\"{header_include}\""]

        source_buf.write("\n")
        header_buf.write("\n")

        for include in includes:
            header_buf.write(f"#include {include}\n")

        for include in source_includes:
            source_buf.write(f"#include {include}\n")

        source_buf.write("\n")
        header_buf.write("\n")

        for ns in namespace:
            header_buf.write(f"namespace {ns} {{ \n")
            source_buf.write(f"namespace {ns} {{ \n")

        header_buf.write("\n")
        source_buf.write("\n")

        for defn in defs:
            self.generate_object_def(header_buf, source_buf, defn)

        for ns in reversed(namespace):
            header_buf.write(f"}} // namespace {ns} \n")
            source_buf.write(f"}} // namespace {ns} \n")

        header_buf.write(f"#endif  // {header_value}\n")

    def generate_object_def(self, header_buf: IO[Any], source_buf: IO[Any], object_def: ObjectDefinition) -> None:
        header_buf.write(f"class {object_def.name};\n")

        if object_def.docs:
            header_buf.write(object_def.docs)
            header_buf.write("\n")

        self.generate_payload_decl(header_buf, object_def)
        self.generate_ref_decl(header_buf, object_def)
        self.generate_impl(source_buf, object_def)

    def generate_payload_decl(self, header_buf: IO[Any], object_def: ObjectDefinition) -> None:
        ref = object_def.ref_name()
        payload = object_def.payload_name()
        parent_ref = object_def.parent_ref_name()
        parent_payload = object_def.parent_payload_name()

        header_buf.write(f"class {payload} : public {parent_payload} {{\n")
        header_buf.write(" public:\n")

        for field in object_def.fields:
            header_buf.write(f"{4 * ' '}{field.field_type} {field.field_name};\n")

        header_buf.write(f"{4 * ' '}void VisitAttrs(AttrVisitor* v) {{\n")
        for field in object_def.fields:
            header_buf.write(f"{8 * ' '}v->Visit(\"{field.field_name}\", &{field.field_name});\n")
        header_buf.write(f"{4 * ' '}}}\n")

        self.generate_equal_and_hash(header_buf, object_def)

        header_buf.write(f"{4 * ' '}static constexpr const char* _type_key = \"{object_def.type_key()}\";\n")
        header_buf.write(f"{4 * ' '}static constexpr const bool _type_has_method_sequal_reduce = true;\n")
        header_buf.write(f"{4 * ' '}static constexpr const bool _type_has_method_shash_reduce = true;\n")

        if object_def.final:
            macro_name = "TVM_DECLARE_FINAL_OBJECT_INFO"
        else:
            macro_name = "TVM_DECLARE_BASE_OBJECT_INFO"

        header_buf.write(f"{4 * ' '}{macro_name}({object_def.payload_name()}, {parent_payload});\n")

        header_buf.write("};\n\n")

    def generate_equal_and_hash(self, header_buf: IO[Any], object_def: ObjectDefinition) -> None:
        # Equality
        header_buf.write(f"{4 * ' '}bool SEqualReduce(const {object_def.payload_name()}* other, SEqualReducer equal) const {{\n")
        header_buf.write(f"{8 * ' '}return")

        check_equal_fields = [f for f in object_def.fields if f.use_in_sequal_reduce]
        if len(check_equal_fields):
            has_bindings = any([f.is_binding for f in check_equal_fields])
            if has_bindings:
                raise Exception("add MarkNodeGraph")

            for i, field in enumerate(check_equal_fields):
                if field.use_in_sequal_reduce:  # Whether this field should be included in the structural equality
                    if has_bindings and field.is_binding:
                        equal_method = "DefEqual"
                    else:
                        equal_method = "equal"

                    header_buf.write(f" {equal_method}({field.field_name}, other->{field.field_name})")
                    if i != len(check_equal_fields) - 1:
                        header_buf.write(" && ")
        else:
            header_buf.write(" true")

        header_buf.write(";\n")
        header_buf.write(f"{4 * ' '}}}\n")

        # Hashing
        header_buf.write(f"{4 * ' '}void SHashReduce(SHashReducer hash_reduce) const {{\n")
        for field in object_def.fields:
            header_buf.write(f"{8 * ' '}hash_reduce({field.field_name});\n")
        header_buf.write(f"{4 * ' '}}}\n")

    def generate_printing(self, source_buffer: IO[Any], object_def: ObjectDefinition) -> None:
        source_buffer.write("TVM_STATIC_IR_FUNCTOR(ReprPrinter, vtable)\n")
        source_buffer.write(f".set_dispatch<{object_def.payload_name()}>([](const ObjectRef& ref, ReprPrinter* p) {{\n")
        source_buffer.write(f"{4 * ' '}auto* node = static_cast<const {object_def.payload_name()}*>(ref.get());\n")
        source_buffer.write(f"{4 * ' '}p->stream << \"{object_def.ref_name()}(\"")
        for field in object_def.fields:
            source_buffer.write(f"<< node->{field.field_name} << \",\"")
        source_buffer.write("\")\";\n")
        source_buffer.write("});\n\n")

    def generate_ref_decl(self, header_buf: IO[Any], object_def: ObjectDefinition) -> None:
        ref = object_def.ref_name()
        payload = object_def.payload_name()
        parent_ref = object_def.parent_ref_name()
        parent_payload = object_def.parent_payload_name()

        header_buf.write(f"class {ref} : public {parent_ref} {{\n")
        header_buf.write(" public:\n")

        if len(object_def.fields):
            self.generate_ctor_decl(header_buf, object_def)

        # TODO(@jroesch): ast nodes should be non-nullable need to fix default ctor issue
        # header_buf.write(f"{4 * ' '}TVM_DEFINE_NOTNULLABLE_OBJECT_REF_METHODS")
        header_buf.write(f"{4 * ' '}TVM_DEFINE_OBJECT_REF_METHODS")

        header_buf.write(f"({ref}, {parent_ref}, {payload});\n")

        header_buf.write("};\n\n")

    def generate_ctor_decl(self, header_buf: IO[Any], object_def: ObjectDefinition) -> None:
        ref = object_def.ref_name()
        header_buf.write(f"{4 * ' '}TVM_DLL {ref}(\n")
        for i, field in enumerate(object_def.fields):
            header_buf.write(f"{8 * ' '}{field.field_type} {field.field_name}")
            if i != len(object_def.fields) - 1:
                header_buf.write(f",\n")
        header_buf.write(f"{4 * ' '});\n")

    def generate_impl(self, source_buf: IO[Any], object_def: ObjectDefinition) -> None:
        ref = object_def.ref_name()
        payload = object_def.payload_name()
        parent_ref = object_def.parent_ref_name()
        parent_payload = object_def.parent_payload_name()

        if len(object_def.fields):
            self.generate_ctor_impl(source_buf, object_def)

        source_buf.write(f"TVM_REGISTER_NODE_TYPE({payload});\n\n")

        source_buf.write(f"TVM_REGISTER_GLOBAL(\"{object_def.ctor_pf()}\")")
        source_buf.write(f".set_body_typed([]")

        source_buf.write(f"(")
        for i, field in enumerate(object_def.fields):
            source_buf.write(f"{field.field_type} {field.field_name}")
            if i != len(object_def.fields) - 1:
                source_buf.write(f",")
        source_buf.write(f") {{\n")
        source_buf.write(f"{4 * ' '}return {ref}(")

        for i, field in enumerate(object_def.fields):
            source_buf.write(f"{field.field_name}")
            if i != len(object_def.fields) - 1:
                source_buf.write(f",")
        source_buf.write(");\n")
        source_buf.write(f"}});\n\n")

        self.generate_printing(source_buf, object_def)

    def generate_ctor_impl(self, source_buf: IO[Any], object_def: ObjectDefinition) -> None:
        ref = object_def.ref_name()
        payload = object_def.payload_name()

        source_buf.write(f"{ref}::{ref}(\n")
        for i, field in enumerate(object_def.fields):
            source_buf.write(f"{4 * ' '}{field.field_type} {field.field_name}")
            if i != len(object_def.fields) - 1:
                source_buf.write(f",\n")
        source_buf.write(f") {{\n")

        source_buf.write(f"{4 * ' '}ObjectPtr<{payload}> n = make_object<{payload}>();\n")

        for field in object_def.fields:
            name = field.field_name
            source_buf.write(f"{4 * ' '}n->{name} = std::move({name});\n")
        source_buf.write(f"{4 * ' '}data_ = std::move(n);\n")
        source_buf.write("}\n\n")
