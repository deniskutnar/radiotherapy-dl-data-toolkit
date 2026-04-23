using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Data.SqlClient;
using System.Collections.Generic;
using System.Globalization;
using VMS.TPS.Common.Model.API;
using VMS.TPS.Common.Model.Types;

[assembly: ESAPIScript(IsWriteable = true)]

namespace LymphomaRtScripting.BaselineReconstruction
{
    /// <summary>
    /// Research baseline reconstruction script used for the "plan setup and optimisation"
    /// step of the workflow.
    ///
    /// Input:
    /// - cohort CSV with plan metadata
    /// - parameter text files exported in the previous step
    /// - transferred CT / RTSTRUCT objects already available in the research Eclipse instance
    ///
    /// Output:
    /// - recreated research plan with copied objectives, calculated MLC motion, and dose
    /// - updated cohort CSV status marker (e.g. Done)
    ///
    /// Sensitive infrastructure values below are intentionally placeholders and must be
    /// replaced locally.
    /// </summary>
    class Program
    {
        private const string ResearchCourseId = "C99_RESEARCH";
        private const string MachineId = "REPLACE_MACHINE_ID";
        private const string EnergyMode = "6X";
        private const int DoseRate = 600;
        private const string Technique = "STATIC";
        private const string MlcId = "REPLACE_MLC_ID";
        private const int OptimizationIterations = 2500;
        private const string DoseModel = "accAcurosXB";
        private const string OptimizerModel = "accPO";
        private const string LeafMotionModel = "Varian Leaf Motion Calculator [18.0.0]";
        private const string CtScannerId = "REPLACE_CT_SCANNER_ID";

        // Replace locally with your research SQL endpoint if patient lookup by Series UID is needed.
        private const string SqlServer = "REPLACE_SQL_SERVER";
        private const string SqlDatabase = "REPLACE_SQL_DATABASE";
        private const string SqlUsername = "REPLACE_SQL_USERNAME";
        private const string SqlPassword = "REPLACE_SQL_PASSWORD";

        [STAThread]
        static void Main(string[] args)
        {
            try
            {
                using (Application app = Application.CreateApplication())
                {
                    Execute(app, args);
                }
            }
            catch (Exception e)
            {
                Console.Error.WriteLine(e.ToString());
            }
        }

        static void Execute(Application app, string[] args)
        {
            string cohortCsv = args.Length > 0 ? args[0] : @"examples\filtered_records_UID.example.csv";
            string parameterDirectory = args.Length > 1 ? args[1] : @"examples\parameter_pool_UID";
            int startingRow = args.Length > 2 ? int.Parse(args[2], CultureInfo.InvariantCulture) : 1;
            int endingRow = args.Length > 3 ? int.Parse(args[3], CultureInfo.InvariantCulture) : 3;

            app.ClosePatient();

            string[] lines = File.ReadAllLines(cohortCsv);
            int processedCount = 0;

            for (int desiredRow = startingRow; desiredRow <= endingRow; desiredRow++)
            {
                try
                {
                    if (desiredRow < 0 || desiredRow >= lines.Length)
                    {
                        continue;
                    }

                    string[] values = ParseCsvLine(lines[desiredRow]);
                    if (values.Length < 3)
                    {
                        Console.WriteLine($"Skipping row {desiredRow}: expected at least 3 columns.");
                        continue;
                    }

                    string patientIdFromCsv = values[0];
                    string planIdOriginal = values[1];
                    string courseIdFromCsv = values[2];
                    string safePlanId = planIdOriginal.Replace(':', '~').Replace(',', '~');
                    string parameterFileName = $"{patientIdFromCsv}_{courseIdFromCsv}_{safePlanId}_parameters.txt";
                    string parameterFile = Path.Combine(parameterDirectory, parameterFileName);

                    Console.WriteLine("=============================================================");
                    Console.WriteLine($"Processing row: {desiredRow}");
                    Console.WriteLine($"Parameter file: {parameterFile}");

                    if (!File.Exists(parameterFile))
                    {
                        Console.WriteLine("Parameter file not found. Skipping row.");
                        continue;
                    }

                    PlanParameterBundle bundle = ReadParameterBundle(parameterFile);
                    PrintBundleSummary(bundle);

                    string resolvedPatientId = ResolvePatientIdFromSeriesUid(bundle.ImageSeriesUid);
                    if (string.IsNullOrWhiteSpace(resolvedPatientId))
                    {
                        resolvedPatientId = patientIdFromCsv;
                    }

                    Console.WriteLine($"Resolved patient ID: {resolvedPatientId}");

                    Patient patient = app.OpenPatientById(resolvedPatientId);
                    if (patient == null)
                    {
                        throw new ApplicationException("Patient could not be opened in the research Eclipse instance.");
                    }

                    try
                    {
                        var match = FindMatchingImageAndStructureSet(patient, bundle);
                        if (match.ImageSeries == null || match.StructureSet == null)
                        {
                            throw new ApplicationException("Could not match transferred CT / RTSTRUCT data by UID.");
                        }

                        patient.BeginModifications();

                        StructureSet newStructureSet = CopyStructureSetForResearch(match.StructureSet);
                        Course course = GetOrCreateCourse(patient, ResearchCourseId);
                        ExternalPlanSetup newPlan = course.AddExternalPlanSetup(newStructureSet);
                        newPlan.Id = planIdOriginal;

                        Console.WriteLine($"Created course: {course.Id}");
                        Console.WriteLine($"Created plan: {newPlan.Id}");

                        if (string.IsNullOrEmpty(match.ImageSeries.ImagingDeviceId))
                        {
                            match.ImageSeries.SetImagingDevice(CtScannerId);
                            Console.WriteLine("Assigned imaging device to matched CT series.");
                        }

                        ConfigureBeams(newPlan, bundle.IsoCoordinates);
                        newPlan.SetPrescription(
                            bundle.NumberOfFractions,
                            new DoseValue(bundle.DosePerFractionGy, DoseValue.DoseUnit.Gy),
                            bundle.TreatmentPercentage);

                        ApplyObjectives(newPlan, newStructureSet, bundle.ObjectiveRows);
                        ConfigureModels(newPlan);
                        RunOptimisationAndDoseCalculation(newPlan);
                        newPlan.PlanNormalizationValue = bundle.PlanNormalizationValue;

                        app.SaveModifications();
                        Console.WriteLine("Plan reconstruction completed successfully.");
                    }
                    finally
                    {
                        app.ClosePatient();
                    }

                    lines[desiredRow] = AppendStatusMarker(lines[desiredRow], "Done");
                    File.WriteAllLines(cohortCsv, lines);

                    processedCount += 1;
                    Console.WriteLine($"Completed rows so far: {processedCount}");
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"Error processing row {desiredRow}: {ex.Message}");
                    Console.Error.WriteLine(ex.StackTrace);
                    app.ClosePatient();
                }
            }

            Console.WriteLine("All requested rows processed.");
            Console.Read();
        }

        static string[] ParseCsvLine(string line)
        {
            var values = new List<string>();
            var sb = new StringBuilder();
            bool inQuotes = false;

            foreach (char c in line)
            {
                if (c == '"')
                {
                    inQuotes = !inQuotes;
                }
                else if (c == ',' && !inQuotes)
                {
                    values.Add(sb.ToString());
                    sb.Clear();
                }
                else
                {
                    sb.Append(c);
                }
            }

            values.Add(sb.ToString());
            return values.ToArray();
        }

        static PlanParameterBundle ReadParameterBundle(string parameterFile)
        {
            string[] records = File.ReadAllLines(parameterFile);
            if (records.Length < 12)
            {
                throw new ApplicationException("Parameter file is incomplete.");
            }

            return new PlanParameterBundle
            {
                ImageSeriesUid = records[0],
                ImageStudyUid = records[1],
                StructureSetUid = records[2],
                StructureSetSeriesUid = records[3],
                StructureSetStudyUid = records[4],
                IsoCoordinates = new VVector(
                    Convert.ToDouble(records[5], CultureInfo.InvariantCulture),
                    Convert.ToDouble(records[6], CultureInfo.InvariantCulture),
                    Convert.ToDouble(records[7], CultureInfo.InvariantCulture)),
                NumberOfFractions = Convert.ToInt32(records[8], CultureInfo.InvariantCulture),
                TreatmentPercentage = Convert.ToDouble(records[9], CultureInfo.InvariantCulture),
                DosePerFractionGy = Convert.ToDouble(records[10], CultureInfo.InvariantCulture),
                PlanNormalizationValue = Convert.ToInt32(records[11], CultureInfo.InvariantCulture),
                ObjectiveRows = records.Skip(12).ToArray()
            };
        }

        static void PrintBundleSummary(PlanParameterBundle bundle)
        {
            Console.WriteLine("Re-planning parameters");
            Console.WriteLine($"Image Series UID: {bundle.ImageSeriesUid}");
            Console.WriteLine($"Image Study UID: {bundle.ImageStudyUid}");
            Console.WriteLine($"StructSet UID: {bundle.StructureSetUid}");
            Console.WriteLine($"StructSet Series UID: {bundle.StructureSetSeriesUid}");
            Console.WriteLine($"StructSet Study UID: {bundle.StructureSetStudyUid}");
            Console.WriteLine($"ISO: {bundle.IsoCoordinates.x}, {bundle.IsoCoordinates.y}, {bundle.IsoCoordinates.z}");
            Console.WriteLine($"Fractions: {bundle.NumberOfFractions}");
            Console.WriteLine($"Treatment percentage: {bundle.TreatmentPercentage}");
            Console.WriteLine($"Dose per fraction [Gy]: {bundle.DosePerFractionGy}");
            Console.WriteLine($"Normalization value: {bundle.PlanNormalizationValue}");
            Console.WriteLine($"Objectives: {bundle.ObjectiveRows.Length}");
            Console.WriteLine();
        }

        static string ResolvePatientIdFromSeriesUid(string imageSeriesUid)
        {
            string connectionString = $"Data Source={SqlServer};Initial Catalog={SqlDatabase};User ID={SqlUsername};Password={SqlPassword}";

            if (connectionString.Contains("REPLACE_"))
            {
                Console.WriteLine("SQL lookup skipped because placeholder credentials are still present.");
                return null;
            }

            using (var connection = new SqlConnection(connectionString))
            {
                connection.Open();

                string query = @"
                    SELECT TOP 1 Patient.PatientId
                    FROM Patient, Study, Series
                    WHERE Study.PatientSer = Patient.PatientSer
                      AND Series.StudySer = Study.StudySer
                      AND Series.SeriesUID = @SeriesUID";

                using (var command = new SqlCommand(query, connection))
                {
                    command.Parameters.AddWithValue("@SeriesUID", imageSeriesUid);
                    object result = command.ExecuteScalar();
                    return result == null ? null : result.ToString();
                }
            }
        }

        static ImageAndStructureMatch FindMatchingImageAndStructureSet(Patient patient, PlanParameterBundle bundle)
        {
            Series matchingImageSeries = null;
            StructureSet matchingStructureSet = null;

            if (bundle.ImageStudyUid == bundle.StructureSetStudyUid)
            {
                Console.WriteLine("Study UID matches for CT and RTSTRUCT.");
            }

            foreach (Study study in patient.Studies)
            {
                foreach (Series series in study.Series)
                {
                    if (series.UID == bundle.ImageSeriesUid && study.UID == bundle.ImageStudyUid)
                    {
                        matchingImageSeries = series;
                        Console.WriteLine("Matched CT image series.");
                        Console.WriteLine($"Series UID: {series.UID}");
                        Console.WriteLine($"Study UID: {study.UID}");
                    }
                }
            }

            foreach (StructureSet structureSet in patient.StructureSets)
            {
                if (structureSet.UID == bundle.StructureSetUid &&
                    structureSet.SeriesUID == bundle.StructureSetSeriesUid &&
                    structureSet.Series.Study.UID == bundle.StructureSetStudyUid)
                {
                    matchingStructureSet = structureSet;
                    Console.WriteLine("Matched RTSTRUCT.");
                    Console.WriteLine($"StructSet UID: {structureSet.UID}");
                    Console.WriteLine($"Series UID: {structureSet.SeriesUID}");
                    Console.WriteLine($"Study UID: {structureSet.Series.Study.UID}");
                    break;
                }
            }

            return new ImageAndStructureMatch
            {
                ImageSeries = matchingImageSeries,
                StructureSet = matchingStructureSet
            };
        }

        static StructureSet CopyStructureSetForResearch(StructureSet source)
        {
            StructureSet newStructureSet = source.Image.CreateNewStructureSet();

            foreach (Structure structure in source.Structures)
            {
                Console.WriteLine($"Copying structure: {structure.Id} [{structure.DicomType}]");

                if (structure.DicomType == "SUPPORT")
                {
                    continue;
                }

                string dicomType = structure.DicomType;
                if (dicomType == "BOLUS")
                {
                    dicomType = "ORGAN";
                }
                if (string.IsNullOrWhiteSpace(dicomType))
                {
                    dicomType = "CONTROL";
                }

                Structure newStructure = newStructureSet.AddStructure(dicomType, structure.Id);
                newStructure.SegmentVolume = structure.SegmentVolume;
            }

            return newStructureSet;
        }

        static Course GetOrCreateCourse(Patient patient, string courseId)
        {
            Course course = patient.Courses.FirstOrDefault(c => c.Id == courseId);
            if (course == null)
            {
                course = patient.AddCourse();
                course.Id = courseId;
            }
            return course;
        }

        static void ConfigureBeams(ExternalPlanSetup plan, VVector isoCoordinates)
        {
            var machineParameters = new ExternalBeamMachineParameters(
                MachineId,
                EnergyMode,
                DoseRate,
                Technique,
                null);

            double[] gantryAngles = new double[] { 0, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240, 264, 288, 312, 336 };
            foreach (double gantryAngle in gantryAngles)
            {
                plan.AddStaticBeam(machineParameters, new VRect<double>(-100, -100, 100, 100), 0, gantryAngle, 0, isoCoordinates);
            }
        }

        static void ApplyObjectives(ExternalPlanSetup plan, StructureSet structureSet, IEnumerable<string> objectiveRows)
        {
            foreach (string objectiveString in objectiveRows)
            {
                if (string.IsNullOrWhiteSpace(objectiveString))
                {
                    continue;
                }

                string[] parts = objectiveString.Split(',');
                if (parts.Length < 5)
                {
                    Console.WriteLine($"Skipping malformed objective row: {objectiveString}");
                    continue;
                }

                string structureId = parts[0].Trim();
                string operatorString = parts[1].Trim();
                string doseValueString = parts[2].Replace("Gy", "").Trim();
                double doseValue = double.Parse(doseValueString, CultureInfo.InvariantCulture);
                double volume = double.Parse(parts[3], CultureInfo.InvariantCulture);
                double priority = double.Parse(parts[4], CultureInfo.InvariantCulture);

                OptimizationObjectiveOperator op = operatorString.Equals("Upper", StringComparison.OrdinalIgnoreCase)
                    ? OptimizationObjectiveOperator.Upper
                    : OptimizationObjectiveOperator.Lower;

                Structure objectiveStructure = structureSet.Structures.SingleOrDefault(st => st.Id == structureId);
                if (objectiveStructure == null)
                {
                    Console.WriteLine($"Objective skipped because structure was not found: {structureId}");
                    continue;
                }

                plan.OptimizationSetup.AddPointObjective(
                    objectiveStructure,
                    op,
                    new DoseValue(doseValue, DoseValue.DoseUnit.Gy),
                    volume,
                    priority);
            }
        }

        static void ConfigureModels(ExternalPlanSetup plan)
        {
            plan.SetCalculationModel(CalculationType.PhotonVolumeDose, DoseModel);
            plan.SetCalculationModel(CalculationType.PhotonLeafMotions, LeafMotionModel);
            plan.SetCalculationModel(CalculationType.PhotonIMRTOptimization, OptimizerModel);
            plan.SetCalculationOption(DoseModel, "PlanDoseCalculation", "OFF");
        }

        static void RunOptimisationAndDoseCalculation(ExternalPlanSetup plan)
        {
            var options = new OptimizationOptionsIMRT(
                OptimizationIterations,
                OptimizationOption.RestartOptimization,
                OptimizationConvergenceOption.TerminateIfConverged,
                MlcId);

            Console.WriteLine("Running IMRT optimisation...");
            plan.Optimize(options);

            if (options.ConvergenceOption == OptimizationConvergenceOption.TerminateIfConverged)
            {
                Console.WriteLine("Optimisation configured to terminate on convergence.");
            }

            Console.WriteLine("Calculating MLC motion...");
            plan.CalculateLeafMotions();

            Console.WriteLine("Calculating dose...");
            plan.CalculateDose();
        }

        static string AppendStatusMarker(string line, string marker)
        {
            if (line.Contains("," + marker) || line.EndsWith(marker, StringComparison.OrdinalIgnoreCase))
            {
                return line;
            }

            return line + "," + marker;
        }

        class PlanParameterBundle
        {
            public string ImageSeriesUid { get; set; }
            public string ImageStudyUid { get; set; }
            public string StructureSetUid { get; set; }
            public string StructureSetSeriesUid { get; set; }
            public string StructureSetStudyUid { get; set; }
            public VVector IsoCoordinates { get; set; }
            public int NumberOfFractions { get; set; }
            public double TreatmentPercentage { get; set; }
            public double DosePerFractionGy { get; set; }
            public int PlanNormalizationValue { get; set; }
            public string[] ObjectiveRows { get; set; }
        }

        class ImageAndStructureMatch
        {
            public Series ImageSeries { get; set; }
            public StructureSet StructureSet { get; set; }
        }
    }
}
