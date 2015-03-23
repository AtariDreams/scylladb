#!/usr/bin/python3
#
# This file is open source software, licensed to you under the terms
# of the Apache License, Version 2.0 (the "License").  See the NOTICE file
# distributed with this work for additional information regarding copyright
# ownership.  You may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
import os, os.path, textwrap, argparse, sys, shlex, subprocess, tempfile, re

configure_args = str.join(' ', [shlex.quote(x) for x in sys.argv[1:]])

def add_tristate(arg_parser, name, dest, help):
    arg_parser.add_argument('--enable-' + name, dest = dest, action = 'store_true', default = None,
                            help = 'Enable ' + help)
    arg_parser.add_argument('--disable-' + name, dest = dest, action = 'store_false', default = None,
                            help = 'Disable ' + help)

def apply_tristate(var, test, note, missing):
    if (var is None) or var:
        if test():
            return True
        elif var == True:
            print(missing)
            sys.exit(1)
        else:
            print(note)
            return False
    return False

def try_compile(compiler, source = '', flags = []):
    with tempfile.NamedTemporaryFile() as sfile:
        sfile.file.write(bytes(source, 'utf-8'))
        sfile.file.flush()
        return subprocess.call([compiler, '-x', 'c++', '-o', '/dev/null', '-c', sfile.name] + flags,
                               stdout = subprocess.DEVNULL,
                               stderr = subprocess.DEVNULL) == 0

def warning_supported(warning, compiler):
    # gcc ignores -Wno-x even if it is not supported
    adjusted = re.sub('^-Wno-', '-W', warning)
    return try_compile(flags = [adjusted], compiler = compiler)

def debug_flag(compiler):
    src_with_auto = textwrap.dedent('''\
        template <typename T>
        struct x { auto f() {} };

        x<int> a;
        ''')
    if try_compile(source = src_with_auto, flags = ['-g', '-std=gnu++1y'], compiler = compiler):
        return '-g'
    else:
        print('Note: debug information disabled; upgrade your compiler')
        return ''

class Thrift(object):
    def __init__(self, source, service):
        self.source = source
        self.service = service
    def generated(self, gen_dir):
        basename = os.path.splitext(os.path.basename(self.source))[0]
        files = [basename + '_' + ext
                 for ext in ['types.cpp', 'types.h', 'constants.cpp', 'constants.h']]
        files += [self.service + ext
                  for ext in ['.cpp', '.h']]
        return [os.path.join(gen_dir, file) for file in files]
    def headers(self, gen_dir):
        return [x for x in self.generated(gen_dir) if x.endswith('.h')]
    def sources(self, gen_dir):
        return [x for x in self.generated(gen_dir) if x.endswith('.cpp')]
    def objects(self, gen_dir):
        return [x.replace('.cpp', '.o') for x in self.sources(gen_dir)]
    def endswith(self, end):
        return self.source.endswith(end)

class Antlr3Grammar(object):
    def __init__(self, source):
        self.source = source
    def generated(self, gen_dir):
        basename = os.path.splitext(self.source)[0]
        files = [basename + ext
                 for ext in ['Lexer.cpp', 'Lexer.hpp', 'Parser.cpp', 'Parser.hpp']]
        return [os.path.join(gen_dir, file) for file in files]
    def headers(self, gen_dir):
        return [x for x in self.generated(gen_dir) if x.endswith('.hpp')]
    def sources(self, gen_dir):
        return [x for x in self.generated(gen_dir) if x.endswith('.cpp')]
    def objects(self, gen_dir):
        return [x.replace('.cpp', '.o') for x in self.sources(gen_dir)]
    def endswith(self, end):
        return self.source.endswith(end)

modes = {
    'debug': {
        'sanitize': '-fsanitize=address -fsanitize=leak -fsanitize=undefined',
        'sanitize_libs': '-lubsan -lasan',
        'opt': '-O0 -DDEBUG -DDEFAULT_ALLOCATOR',
        'libs': '',
    },
    'release': {
        'sanitize': '',
        'sanitize_libs': '',
        'opt': '-O2',
        'libs': '',
    },
}

urchin_tests = [
    'tests/urchin/mutation_test',
    'tests/urchin/types_test',
    'tests/perf/perf_mutation',
    'tests/perf/perf_cql_parser',
    'tests/urchin/cql_query_test',
    'tests/test-serialization',
    'tests/urchin/sstable_test',
    'tests/urchin/commitlog_test',
    'tests/cartesian_product_test',
]

tests = [
    'tests/test-reactor',
    'tests/fileiotest',
    'tests/directory_test',
    'tests/linecount',
    'tests/echotest',
    'tests/l3_test',
    'tests/ip_test',
    'tests/timertest',
    'tests/tcp_test',
    'tests/futures_test',
    'tests/smp_test',
    'tests/udp_server',
    'tests/udp_client',
    'tests/blkdiscard_test',
    'tests/sstring_test',
    'tests/httpd',
    'tests/memcached/test_ascii_parser',
    'tests/tcp_server',
    'tests/tcp_client',
    'tests/allocator_test',
    'tests/output_stream_test',
    'tests/udp_zero_copy',
    'tests/shared_ptr_test',
    'tests/slab_test',
    'tests/fstream_test',
    'tests/map_reduce_test',
    'tests/rpc',
    ]

apps = [
    'apps/httpd/httpd',
    'seastar',
    'apps/seawreck/seawreck',
    'apps/memcached/memcached',
    ]

tests += urchin_tests

all_artifacts = apps + tests + ['libseastar.a', 'seastar.pc']

arg_parser = argparse.ArgumentParser('Configure seastar')
arg_parser.add_argument('--static', dest = 'static', action = 'store_const', default = '',
                        const = '-static',
                        help = 'Static link (useful for running on hosts outside the build environment')
arg_parser.add_argument('--pie', dest = 'pie', action = 'store_true',
                        help = 'Build position-independent executable (PIE)')
arg_parser.add_argument('--so', dest = 'so', action = 'store_true',
                        help = 'Build shared object (SO) instead of executable')
arg_parser.add_argument('--mode', action='store', choices=list(modes.keys()) + ['all'], default='all')
arg_parser.add_argument('--with', dest='artifacts', action='append', choices=all_artifacts, default=[])
arg_parser.add_argument('--cflags', action = 'store', dest = 'user_cflags', default = '',
                        help = 'Extra flags for the C++ compiler')
arg_parser.add_argument('--ldflags', action = 'store', dest = 'user_ldflags', default = '',
                        help = 'Extra flags for the linker')
arg_parser.add_argument('--compiler', action = 'store', dest = 'cxx', default = 'g++',
                        help = 'C++ compiler path')
arg_parser.add_argument('--with-osv', action = 'store', dest = 'with_osv', default = '',
                        help = 'Shortcut for compile for OSv')
arg_parser.add_argument('--dpdk-target', action = 'store', dest = 'dpdk_target', default = '',
                        help = 'Path to DPDK SDK target location (e.g. <DPDK SDK dir>/x86_64-native-linuxapp-gcc)')
arg_parser.add_argument('--debuginfo', action = 'store', dest = 'debuginfo', type = int, default = 1,
                        help = 'Enable(1)/disable(0)compiler debug information generation')
add_tristate(arg_parser, name = 'hwloc', dest = 'hwloc', help = 'hwloc support')
add_tristate(arg_parser, name = 'xen', dest = 'xen', help = 'Xen support')
args = arg_parser.parse_args()

libnet = [
    'net/proxy.cc',
    'net/virtio.cc',
    'net/dpdk.cc',
    'net/ip.cc',
    'net/ethernet.cc',
    'net/arp.cc',
    'net/native-stack.cc',
    'net/ip_checksum.cc',
    'net/udp.cc',
    'net/tcp.cc',
    'net/dhcp.cc',
    ]

core = [
    'core/reactor.cc',
    'core/fstream.cc',
    'core/posix.cc',
    'core/memory.cc',
    'core/resource.cc',
    'core/scollectd.cc',
    'core/app-template.cc',
    'core/dpdk_rte.cc',
    'util/conversions.cc',
    'net/packet.cc',
    'net/posix-stack.cc',
    'tests/test_runner.cc',
    'net/net.cc',
    'rpc/rpc.cc',
    ]

defines = []
libs = '-laio -lboost_program_options -lboost_system -lstdc++ -lm -lboost_unit_test_framework -lboost_thread -lcryptopp -lrt'
hwloc_libs = '-lhwloc -lnuma -lpciaccess -lxml2 -lz'

def have_xen():
    source  = '#include <stdint.h>\n'
    source += '#include <xen/xen.h>\n'
    source += '#include <xen/sys/evtchn.h>\n'
    source += '#include <xen/sys/gntdev.h>\n'
    source += '#include <xen/sys/gntalloc.h>\n'

    return try_compile(compiler = args.cxx, source = source)

if apply_tristate(args.xen, test = have_xen,
                  note = 'Note: xen-devel not installed.  No Xen support.',
                  missing = 'Error: required package xen-devel not installed.'):
    libs += ' -lxenstore'
    defines.append("HAVE_XEN")
    libnet += [ 'net/xenfront.cc' ]
    core += [
                'core/xen/xenstore.cc',
                'core/xen/gntalloc.cc',
                'core/xen/evtchn.cc',
            ]


memcache_base = [
    'apps/memcached/ascii.rl'
] + libnet + core

cassandra_interface = Thrift(source = 'interface/cassandra.thrift', service = 'Cassandra')

urchin_core = (['database.cc',
                 'sstables/sstables.cc',
                 'log.cc',
                 'transport/server.cc',
                 'cql3/abstract_marker.cc',
                 'cql3/cql3.cc',
                 'cql3/cql3_type.cc',
                 'cql3/operation.cc',
                 'cql3/functions/functions.cc',
                 'cql3/statements/schema_altering_statement.cc',
                 'cql3/statements/modification_statement.cc',
                 'cql3/statements/update_statement.cc',
                 'cql3/statements/delete_statement.cc',
                 'cql3/statements/select_statement.cc',
                 'cql3/statements/use_statement.cc',
                 'thrift/handler.cc',
                 'thrift/server.cc',
                 'thrift/thrift_validation.cc',
                 'utils/murmur_hash.cc',
                 'utils/uuid.cc',
                 'types.cc',
                 'validation.cc',
                 'service/storage_proxy.cc',
                 'cql3/operator.cc',
                 'cql3/relation.cc',
                 'cql3/column_identifier.cc',
                 'cql3/constants.cc',
                 'cql3/query_processor.cc',
                 'cql3/query_options.cc',
                 'cql3/single_column_relation.cc',
                 'cql3/column_condition.cc',
                 'cql3/selection/simple_selector.cc',
                 'cql3/selection/selector_factories.cc',
                 'cql3/selection/selection.cc',
                 'cql3/restrictions/statement_restrictions.cc',
                 'db/db.cc',
                 'db/system_keyspace.cc',
                 'db/legacy_schema_tables.cc',
                 'db/commitlog/commitlog.cc',
                 'io/io.cc',
                 'utils/utils.cc',
                 'utils/UUID_gen.cc',
                 'gms/version_generator.cc',
                 'gms/gms.cc',
                 'dht/dht.cc',
                 'dht/i_partitioner.cc',
                 'dht/murmur3_partitioner.cc',
                 'unimplemented.cc',
                 'query.cc',
                 ]
                + [Antlr3Grammar('cql3/Cql.g')]
                + [Thrift('interface/cassandra.thrift', 'Cassandra')]
                + core + libnet)

deps = {
    'libseastar.a' : core + libnet,
    'seastar.pc': [],
    'seastar': ['main.cc'] + urchin_core,
    'tests/test-reactor': ['tests/test-reactor.cc'] + core,
    'apps/httpd/httpd': ['http/common.cc', 'http/routes.cc', 'json/json_elements.cc', 'json/formatter.cc', 'http/matcher.cc', 'http/mime_types.cc', 'http/httpd.cc', 'http/reply.cc', 'http/request_parser.rl', 'apps/httpd/main.cc'] + libnet + core,
    'apps/memcached/memcached': ['apps/memcached/memcache.cc'] + memcache_base,
    'tests/memcached/test_ascii_parser': ['tests/memcached/test_ascii_parser.cc'] + memcache_base,
    'tests/fileiotest': ['tests/fileiotest.cc'] + core,
    'tests/directory_test': ['tests/directory_test.cc'] + core,
    'tests/linecount': ['tests/linecount.cc'] + core,
    'tests/echotest': ['tests/echotest.cc'] + core + libnet,
    'tests/l3_test': ['tests/l3_test.cc'] + core + libnet,
    'tests/ip_test': ['tests/ip_test.cc'] + core + libnet,
    'tests/tcp_test': ['tests/tcp_test.cc'] + core + libnet,
    'tests/timertest': ['tests/timertest.cc'] + core,
    'tests/futures_test': ['tests/futures_test.cc'] + core,
    'tests/smp_test': ['tests/smp_test.cc'] + core,
    'tests/udp_server': ['tests/udp_server.cc'] + core + libnet,
    'tests/udp_client': ['tests/udp_client.cc'] + core + libnet,
    'tests/tcp_server': ['tests/tcp_server.cc'] + core + libnet,
    'tests/tcp_client': ['tests/tcp_client.cc'] + core + libnet,
    'apps/seawreck/seawreck': ['apps/seawreck/seawreck.cc', 'apps/seawreck/http_response_parser.rl'] + core + libnet,
    'tests/blkdiscard_test': ['tests/blkdiscard_test.cc'] + core,
    'tests/sstring_test': ['tests/sstring_test.cc'] + core,
    'tests/httpd': ['http/common.cc', 'http/routes.cc', 'json/json_elements.cc', 'json/formatter.cc', 'http/matcher.cc', 'tests/httpd.cc', 'http/mime_types.cc', 'http/reply.cc'] + core,
    'tests/allocator_test': ['tests/allocator_test.cc', 'core/memory.cc', 'core/posix.cc'],
    'tests/output_stream_test': ['tests/output_stream_test.cc'] + core + libnet,
    'tests/udp_zero_copy': ['tests/udp_zero_copy.cc'] + core + libnet,
    'tests/shared_ptr_test': ['tests/shared_ptr_test.cc'] + core,
    'tests/slab_test': ['tests/slab_test.cc'] + core,
    'tests/fstream_test': ['tests/fstream_test.cc'] + core,
    'tests/map_reduce_test': ['tests/map_reduce_test.cc'] + core,
    'tests/rpc': ['tests/rpc.cc'] + core + libnet,
}

for t in urchin_tests:
    deps[t] = urchin_core + [t + '.cc']

warnings = [
    '-Wno-mismatched-tags',  # clang-only
    ]

# The "--with-osv=<path>" parameter is a shortcut for a bunch of other
# settings:
if args.with_osv:
    args.so = True
    args.hwloc = False
    args.user_cflags = (args.user_cflags +
        ' -DDEFAULT_ALLOCATOR -fvisibility=default -DHAVE_OSV -I' +
        args.with_osv + '/include')

if args.dpdk_target:
    args.user_cflags = (args.user_cflags +
        ' -DHAVE_DPDK -I' +
        args.dpdk_target + '/include -Wno-error=literal-suffix -Wno-literal-suffix -Wno-invalid-offsetof')
    libs += (' -L' + args.dpdk_target + '/lib ' +
        '-Wl,--whole-archive -lrte_pmd_bond -lrte_pmd_vmxnet3_uio -lrte_pmd_virtio_uio -lrte_pmd_i40e -lrte_pmd_ixgbe -lrte_pmd_e1000 -lrte_pmd_ring -Wl,--no-whole-archive -lrte_distributor -lrte_kni -lrte_pipeline -lrte_table -lrte_port -lrte_timer -lrte_hash -lrte_lpm -lrte_power -lrte_acl -lrte_meter -lrte_sched -lrte_kvargs -lrte_mbuf -lrte_ip_frag -lethdev -lrte_eal -lrte_malloc -lrte_mempool -lrte_ring -lrte_cmdline -lrte_cfgfile -lrt -lm -ldl')

warnings = [w
            for w in warnings
            if warning_supported(warning = w, compiler = args.cxx)]

warnings = ' '.join(warnings)

dbgflag = debug_flag(args.cxx) if args.debuginfo else ''

def have_hwloc():
    return try_compile(compiler = args.cxx, source = '#include <hwloc.h>\n#include <numa.h>')

if apply_tristate(args.hwloc, test = have_hwloc,
                  note = 'Note: hwloc-devel/numactl-devel not installed.  No NUMA support.',
                  missing = 'Error: required packages hwloc-devel/numactl-devel not installed.'):
    libs += ' ' + hwloc_libs
    defines.append('HAVE_HWLOC')
    defines.append('HAVE_NUMA')

if args.so:
    args.pie = '-shared'
    args.fpie = '-fpic'
elif args.pie:
    args.pie = '-pie'
    args.fpie = '-fpie'
else:
    args.pie = ''
    args.fpie = ''

defines = ' '.join(['-D' + d for d in defines])

globals().update(vars(args))

total_memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
link_pool_depth = max(int(total_memory / 15e9), 1)

build_modes = modes if args.mode == 'all' else [args.mode]
build_artifacts = all_artifacts if not args.artifacts else args.artifacts

outdir = 'build'
buildfile = 'build.ninja'
os.makedirs(outdir, exist_ok = True)
do_sanitize = True
if args.static:
    do_sanitize = False
with open(buildfile, 'w') as f:
    f.write(textwrap.dedent('''\
        configure_args = {configure_args}
        builddir = {outdir}
        cxx = {cxx}
        cxxflags = -std=gnu++1y {dbgflag} {fpie} -Wall -Werror -fvisibility=hidden -pthread -I. {user_cflags} {warnings} {defines}
        ldflags = {dbgflag} -Wl,--no-as-needed {static} {pie} -fvisibility=hidden -pthread {user_ldflags}
        libs = {libs}
        pool link_pool
            depth = {link_pool_depth}
        rule ragel
            command = ragel -G2 -o $out $in
            description = RAGEL $out
        rule gen
            command = echo -e $text > $out
            description = GEN $out
        ''').format(**globals()))
    for mode in build_modes:
        modeval = modes[mode]
        if modeval['sanitize'] and not do_sanitize:
            print('Note: --static disables debug mode sanitizers')
            modeval['sanitize'] = ''
            modeval['sanitize_libs'] = ''
        f.write(textwrap.dedent('''\
            cxxflags_{mode} = {sanitize} {opt} -I $builddir/{mode}/gen
            libs_{mode} = {libs} {sanitize_libs}
            rule cxx.{mode}
              command = $cxx -MMD -MT $out -MF $out.d $cxxflags $cxxflags_{mode} -c -o $out $in
              description = CXX $out
              depfile = $out.d
            rule link.{mode}
              command = $cxx  $cxxflags_{mode} $ldflags -o $out $in $libs $libs_{mode}
              description = LINK $out
              pool = link_pool
            rule ar.{mode}
              command = rm -f $out; ar cr $out $in; ranlib $out
              description = AR $out
            rule thrift.{mode}
                command = thrift -gen cpp:cob_style -out $builddir/{mode}/gen $in
                description = THRIFT $in
            rule antlr3.{mode}
                command = sed -e '/^#if 0/,/^#endif/d' $in > $builddir/{mode}/gen/$in && antlr3 $builddir/{mode}/gen/$in && sed -i 's/^\\( *\)\\(ImplTraits::CommonTokenType\\* [a-zA-Z0-9_]* = NULL;\\)$$/\\1const \\2/' build/{mode}/gen/${{stem}}Parser.cpp
                description = ANTLR3 $in
            ''').format(mode = mode, **modeval))
        f.write('build {mode}: phony {artifacts}\n'.format(mode = mode,
            artifacts = str.join(' ', ('$builddir/' + mode + '/' + x for x in build_artifacts))))
        compiles = {}
        ragels = {}
        thrifts = set()
        antlr3_grammars = set()
        for binary in build_artifacts:
            srcs = deps[binary]
            objs = ['$builddir/' + mode + '/' + src.replace('.cc', '.o')
                    for src in srcs
                    if src.endswith('.cc')]
            has_thrift = False
            for dep in deps[binary]:
                if isinstance(dep, Thrift):
                    has_thrift = True
                    objs += dep.objects('$builddir/' + mode + '/gen')
                if isinstance(dep, Antlr3Grammar):
                    objs += dep.objects('$builddir/' + mode + '/gen')
            if binary.endswith('.pc'):
                vars = modeval.copy()
                vars.update(globals())
                pc = textwrap.dedent('''\
                        Name: Seastar
                        URL: http://seastar-project.org/
                        Description: Advanced C++ framework for high-performance server applications on modern hardware.
                        Version: 1.0
                        Libs: -L{srcdir}/{builddir} -Wl,--whole-archive -lseastar -Wl,--no-whole-archive {dbgflag} -Wl,--no-as-needed {static} {pie} -fvisibility=hidden -pthread {user_ldflags} {libs} {sanitize_libs}
                        Cflags: -std=gnu++1y {dbgflag} {fpie} -Wall -Werror -fvisibility=hidden -pthread -I{srcdir} -I{srcdir}/{builddir}/gen {user_cflags} {warnings} {defines} {sanitize} {opt}
                        ''').format(builddir = 'build/' + mode, srcdir = os.getcwd(), **vars)
                f.write('build $builddir/{}/{}: gen\n  text = {}\n'.format(mode, binary, repr(pc)))
            elif binary.endswith('.a'):
                f.write('build $builddir/{}/{}: ar.{} {}\n'.format(mode, binary, mode, str.join(' ', objs)))
            else:
                f.write('build $builddir/{}/{}: link.{} {}\n'.format(mode, binary, mode, str.join(' ', objs)))
                if has_thrift:
                    f.write('   libs =  -lthrift -lboost_system $libs\n')
            for src in srcs:
                if src.endswith('.cc'):
                    obj = '$builddir/' + mode + '/' + src.replace('.cc', '.o')
                    compiles[obj] = src
                elif src.endswith('.rl'):
                    hh = '$builddir/' + mode + '/gen/' + src.replace('.rl', '.hh')
                    ragels[hh] = src
                elif src.endswith('.thrift'):
                    thrifts.add(src)
                elif src.endswith('.g'):
                    antlr3_grammars.add(src)
                else:
                    raise Exception('No rule for ' + src)
        for obj in compiles:
            src = compiles[obj]
            gen_headers = list(ragels.keys())
            for th in thrifts:
                gen_headers += th.headers('$builddir/{}/gen'.format(mode))
            for g in antlr3_grammars:
                gen_headers += g.headers('$builddir/{}/gen'.format(mode))
            f.write('build {}: cxx.{} {} || {} \n'.format(obj, mode, src, ' '.join(gen_headers)))
        for hh in ragels:
            src = ragels[hh]
            f.write('build {}: ragel {}\n'.format(hh, src))
        for thrift in thrifts:
            outs = ' '.join(thrift.generated('$builddir/{}/gen'.format(mode)))
            f.write('build {}: thrift.{} {}\n'.format(outs, mode, thrift.source))
            for cc in thrift.sources('$builddir/{}/gen'.format(mode)):
                obj = cc.replace('.cpp', '.o')
                f.write('build {}: cxx.{} {}\n'.format(obj, mode, cc))
        for grammar in antlr3_grammars:
            outs = ' '.join(grammar.generated('$builddir/{}/gen'.format(mode)))
            f.write('build {}: antlr3.{} {}\n  stem = {}\n'.format(outs, mode, grammar.source,
                                                                   grammar.source.rsplit('.', 1)[0]))
            for cc in grammar.sources('$builddir/{}/gen'.format(mode)):
                obj = cc.replace('.cpp', '.o')
                f.write('build {}: cxx.{} {}\n'.format(obj, mode, cc))
    f.write(textwrap.dedent('''\
        rule configure
          command = python3 configure.py $configure_args
          generator = 1
        build build.ninja: configure | configure.py
        rule cscope
            command = find -name '*.[chS]' -o -name "*.cc" -o -name "*.hh" | cscope -bq -i-
            description = CSCOPE
        build cscope: cscope
        default {modes_list}
        ''').format(modes_list = ' '.join(build_modes), **globals()))
