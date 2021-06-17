# create a script to run a customized ND production on the grid
from optparse import OptionParser
import os
import sys

def run_gen( sh, args ):
    # Get the generator stage inputs that are needed
    print >> sh, "mv generator/GNuMIFlux.xml ."
    print >> sh, "mv generator/copy_dune_flux ."
    print >> sh, "mv generator/Messenger_production.xml ."
    print >> sh, "mv geometries/%s.gdml ." % args.geometry

    mode = "neutrino" if args.horn == "FHC" else "antineutrino"
    fluxopt = "--dk2nu" if args.use_dk2nu else ""
    print >> sh, "chmod +x copy_dune_flux"
    print >> sh, "./copy_dune_flux --top %s --flavor %s --maxmb=300 %s" % (args.fluxdir, mode, fluxopt)

    if args.use_dk2nu:  
        # GENIE for some reason doesn't recognize *.dk2nu.root as dk2nu format, but it works if dk2nu is at the front?
        print >> sh, "pushd local_flux_files"
        print >> sh, "for f in *.dk2nu.root"
        print >> sh, "do"
        print >> sh, "  mv \"$f\" \"dk2nu_$f\""
        print >> sh, "done"
        print >> sh, "popd"
  
    # Modify GNuMIFlux.xml to the specified off-axis position
    print >> sh, "sed -i \"s/<beampos> ( 0.0, 0.05387, 6.66 )/<beampos> ( %1.2f, 0.05387, 6.66 )/g\" GNuMIFlux.xml" % args.oa
  
    print >> sh, "export GXMLPATH=${PWD}:${GXMLPATH}"
    print >> sh, "export GNUMIXML=\"GNuMIFlux.xml\""
  
    # Run GENIE
    flux = "dk2nu" if args.use_dk2nu else "gsimple"
    print >> sh, "gevgen_fnal \\"
    print >> sh, "    -f local_flux_files/%s*,DUNEND \\" % flux
    print >> sh, "    -g %s.gdml \\" % args.geometry
    print >> sh, "    -t %s \\" % args.topvol
    print >> sh, "    -L cm -D g_cm3 \\"
    print >> sh, "    -e %g \\" % args.pot
    print >> sh, "    --seed ${SEED} \\"
    print >> sh, "    -r ${RUN} \\"
    print >> sh, "    -o %s \\" % mode
    print >> sh, "    --message-thresholds Messenger_production.xml \\"
    print >> sh, "    --cross-sections ${GENIEXSECPATH}/gxspl-FNALsmall.xml \\"
    print >> sh, "    --event-record-print-level 0 \\"
    print >> sh, "    --event-generator-list Default+CCMEC"

    # Copy the output

def run_g4( sh, args ):
    mode = "neutrino" if args.horn == "FHC" else "antineutrino"

    # Get the input file
    if any(x in stages for x in ["gen", "genie", "generator"]):
        # Then we just made the GENIE file, and it's sitting in the working directory
        print >> sh, "cp %s.${RUN}.ghep.root input_file.ghep.root" % mode
    else:
        # We need to get the input file
        print >> sh, "ifdh %s/genie/%s/%02.0fm/${RDIR}/%s.${RUN}.ghep.root input_file.ghep.root" % (args.indir, args.horn, args.oa, mode)

    # convert to rootracker to run edep-sim
    print >> sh, "gntpc -i input_file.ghep.root -f rootracker --event-record-print-level 0 --message-thresholds Messenger_production.xml"

    # Get edep-sim
    print >> sh, "setup edepsim v3_0_1 -q e20:prof"

    # Get the macro
    print >> sh, "cp geant4/dune-nd.mac ."

    # Get the number of events in the genie file
    # if we're doing overlay, then we want to get the poisson mean and then the number of spills, and be careful not to overshoot
    if args.overlay:
        print >> sh, "MEAN=$(echo \"std::cout << gtree->GetEntries()*(%3.3g/%3.3g) << std::endl;\" | genie -l -b input_file.ghep.root 2>/dev/null  | tail -1)" % (args.spill_pot, args.pot)
        print >> sh, "NSPILL=$(echo \"std::cout << (int)floor(0.9*gtree->GetEntries()/${MEAN}) << std::endl;\" | genie -l -b input_file.ghep.root 2>/dev/null  | tail -1)"

        # change the macro to use mean
        print >> sh, "sed -i \"s/count\/set fixed/cout\/set mean/g\" dune-nd.mac"
        print >> sh, "sed -i \"s/count\/fixed\/number 1/count\/mean\/number ${MEAN}/g\" dune-nd.mac"
        
    else:
        print >> sh, "NSPILL=$(echo \"std::cout << gtree->GetEntries() << std::endl;\" | genie -l -b input_file.ghep.root 2>/dev/null  | tail -1)"

    #Run it
    print >> sh, "edep-sim -C \\"
    print >> sh, "  -g %s.gdml \\" % args.geometry
    print >> sh, "  -o %s.${RUN}.edep.root \\" % mode
    print >> sh, "  -e ${NSPILL} \\"
    print >> sh, "  dune-nd.mac"

def run_larcv( sh, args ):

    mode = "neutrino" if args.horn == "FHC" else "antineutrino"

    # Get the input file, unless we just ran edep-sim and it's sitting in the working directory
    if not any(x in stages for x in ["g4", "geant4", "edepsim", "edep-sim"]):
        print >> sh, "setup edepsim v3_0_1 -q e20:prof"
        print >> sh, "ifdh %s/edep/%s/%02.0fm/${RDIR}/%s.${RUN}.edep.root %s.${RUN}.edep.root" % (args.indir, args.horn, args.oa, mode, mode)

    # Setup edep-sim
    #print >> sh, "pushd edep-sim;source setup.sh;popd"

    # Get larcv stuff
    print >> sh, "ifdh cp %s/larcv2.tar.bz2 larcv2.tar.bz2" % args.tardir
    print >> sh, "bzip2 -d larcv2.tar.bz2"
    print >> sh, "tar -xf larcv2.tar"

    # additional python setup needed
    print >> sh, "setup python_future_six_request  v1_3 -q python2.7-ucs2"

    # run LArCV2
    print >> sh, ". larcv2/configure.sh"
    print >> sh, "supera_dir=${LARCV_BASEDIR}/larcv/app/Supera"
    print >> sh, "python ${supera_dir}/run_supera.py reco/larcv.cfg %s.${RUN}.edep.root" % mode


if __name__ == "__main__":

    user = os.getenv("USER")

    # Make a bash script to run on the grid
    # Start with the template with functions used for all jobs
    template = open("template.sh","r").readlines()
    sh = open( "script.sh", "w" )
    sh.writelines(template)

    parser = OptionParser()

    parser.add_option('--horn', help='FHC or RHC', default="FHC")
    parser.add_option('--horn_current', help='horn current (default is 300 for FHC, -300 for RHC', type = "float", default=None)
    parser.add_option('--geometry', help='Geometry file', default="nd_hall_lar_tms")
    parser.add_option('--topvol', help='Top volume for generating events (gen stage only)', default="volWorld")
    parser.add_option('--pot', help='POT per job', type = "float", default=1.e16)
    parser.add_option('--spill_pot', help='POT per spill', type = "float", default=7.5e13)
    parser.add_option('--first_run', help='First run number to use', default=0, type = "int")
    parser.add_option('--oa', help='Off-axis position in meters', default=0, type = "float")
    parser.add_option('--test', help='Use test mode (interactive job)', default=False, action="store_true")
    parser.add_option('--overlay', help='Simulate full spills (default is single events)', default=False, action="store_true")
    parser.add_option('--stages', help='Production stages (gen+g4+larcv+ana)', default="gen+g4+larcv+ana")
    parser.add_option('--persist', help='Production stages to save to disk(gen+g4+larcv+ana)', default="all")
    parser.add_option('--indir', help='Input file top-directory (if not running gen)', default="/pnfs/dune/persistent/users/%s/nd_production"%user)
    parser.add_option('--tardir', help='Specify a directory where the executables live', default=None)
    parser.add_option('--fluxdir', help='Specify the top-level flux file directory', default="/cvmfs/dune.osgstorage.org/pnfs/fnal.gov/usr/dune/persistent/stash/Flux/g4lbne/v3r5p4/QGSP_BERT/OptimizedEngineeredNov2017")
    parser.add_option('--outdir', help='Top-level output directory', default="/pnfs/dune/persistent/users/%s/nd_production"%user)
    parser.add_option('--use_dk2nu', help='Use full dk2nu flux input (default is gsimple)', action="store_true", default=False)
    parser.add_option('--sam_name', help='Make a sam dataset with this name', default=None)

    (args, dummy) = parser.parse_args()

    mode = "neutrino" if args.horn == "FHC" else "antineutrino"
    hc = 300.
    if args.horn == "RHC":
        hc = -300.
    if args.horn_current is not None:
        hc = args.horn_current
    fluxid = 2
    if args.use_dk2nu:
        fluxid = 1

    # Software setup -- eventually we may want options for this
    print >> sh, "source /cvmfs/dune.opensciencegrid.org/products/dune/setup_dune.sh"
    print >> sh, "setup ifdhc"
    print >> sh, "setup dk2nugenie   v01_06_01f -q debug:e15"
    print >> sh, "setup genie_xsec   v2_12_10   -q DefaultPlusValenciaMEC"
    print >> sh, "setup genie_phyopt v2_12_10   -q dkcharmtau"
    print >> sh, "setup geant4 v4_10_3_p01b -q e15:prof"

    # edep-sim needs to know the location of this file, and also needs to have this location in its path
    print >> sh, "G4_cmake_file=`find ${GEANT4_FQ_DIR}/lib64 -name 'Geant4Config.cmake'`"
    print >> sh, "export Geant4_DIR=`dirname $G4_cmake_file`"
    print >> sh, "export PATH=$PATH:$GEANT4_FQ_DIR/bin"

    # if test mode, run it in a new directory so we don't tarbomb
    # Run number and random seed must be set in the script because the $PROCRESS variable is different for each job
    if args.test:
        print >> sh, "mkdir test;cd test"
        print >> sh, "RUN=%d" % args.first_run
        print >> sh, "SEED=%d" % (1E6*args.oa + args.first_run)
    else:
        print >> sh, "RUN=$((${PROCESS}+%d))" % args.first_run
        print >> sh, "SEED=$((1000000*%d+${RUN}))" % (int(args.oa))

    # Set the run dir in the script, as it can be different for different jobs within one submission if N is large
    print >> sh, "RDIR=$((${RUN} / 1000))"
    print >> sh, "if [ ${RUN} -lt 10000 ]; then"
    print >> sh, "RDIR=0$((${RUN} / 1000))"
    print >> sh, "fi"

    # Get the input files
    if args.tardir is None:
        # Maybe we want to make it default to tarring the working directory?
        print "You must specify a place where the tarballs of input files live with --tardir"
        sys.exit(0)
    else:
        print >> sh, "ifdh cp %s/sim_inputs.tar.gz sim_inputs.tar.gz" % args.tardir
        print >> sh, "tar -xzf sim_inputs.tar.gz"

    stages = (args.stages).lower()
    copylines = []

    # Generator/GENIE stage
    if any(x in stages for x in ["gen", "genie", "generator"]):
        run_gen( sh, args )
        if args.sam_name is not None:
            copylines.append( "generate_sam_json %s.${RUN}.ghep.root ${NSPILL} \"generated\" %s %1.2f %s %s %1.1f %d\n" % (mode, args.sam_name, args.oa, args.geometry, args.topvol, hc, fluxid) )
        if args.persist == "all" or any(x in args.persist for x in ["gen", "genie", "generator"]):
            copylines.append( "ifdh_mkdir_p %s/genie/%s/%02.0fm/${RDIR}\n" % (args.outdir, args.horn, args.oa) )
            copylines.append( "ifdh cp %s.${RUN}.ghep.root %s/genie/%s/%02.0fm/${RDIR}/%s.${RUN}.ghep.root\n" % (mode, args.outdir, args.horn, args.oa, mode) )

    # G4/edep-sim stage
    if any(x in stages for x in ["g4", "geant4", "edepsim", "edep-sim"]):
        run_g4( sh, args )
        if args.sam_name is not None:
            copylines.append( "generate_sam_json %s.${RUN}.edep.root ${NSPILL} \"simulated\" %s %1.2f %s %s %1.1f %d\n" % (mode, args.sam_name, args.oa, args.geometry, args.topvol, hc, fluxid) )
        if args.persist == "all" or any(x in args.persist for x in ["g4", "geant4", "edepsim", "edep-sim"]):
            copylines.append( "ifdh_mkdir_p %s/edep/%s/%02.0fm/${RDIR}\n" % (args.outdir, args.horn, args.oa) )
            copylines.append( "ifdh cp %s.${RUN}.edep.root %s/edep/%s/%02.0fm/${RDIR}/%s.${RUN}.edep.root\n" % (mode, args.outdir, args.horn, args.oa, mode) )

    # LarCV stage
    if any(x in stages for x in ["larcv"]):
        run_larcv( sh, args )
        if args.persist == "all" or any(x in args.persist for x in ["larcv"]):
            copylines.append( "ifdh_mkdir_p %s/larcv/%s/%02.0fm/${RDIR}\n" % (args.outdir, args.horn, args.oa) )
            copylines.append( "ifdh cp larcv.root %s/larcv/%s/%02.0fm/${RDIR}/%s.${RUN}.larcv.root\n" % (args.outdir, args.horn, args.oa, mode) )

    sh.writelines(copylines)

